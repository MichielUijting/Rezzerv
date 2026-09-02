from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import inspect, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import engine
from app.services.password_reset_service import (
    confirm_password_reset,
    request_password_reset,
    validate_password_reset_schema,
)
from app.services.password_service import hash_password, verify_password


USER_ID = "__password_reset_dml_only_user__"
USER_EMAIL = "password-reset-dml-only@example.test"
SESSION_ID = "__password_reset_dml_only_session__"
OLD_PASSWORD = "PasswordResetOld123!"
NEW_PASSWORD = "PasswordResetNew456!"
CLIENT_IP = "203.0.113.55"


def _assert_runtime_context() -> None:
    if os.getenv("MIGRATION_DATABASE_URL"):
        raise AssertionError("DML-only password-reset test must not receive MIGRATION_DATABASE_URL")
    with engine.connect() as conn:
        if conn.dialect.name != "postgresql":
            raise AssertionError(f"PostgreSQL required, got {conn.dialect.name}")
        has_create = bool(
            conn.execute(
                text("SELECT has_schema_privilege(current_user, current_schema(), 'CREATE')")
            ).scalar_one()
        )
        if has_create:
            raise AssertionError("Runtime role unexpectedly has schema CREATE privilege")
    print("POSTGRESQL_PASSWORD_RESET_RUNTIME_CREATE_DENIED_GREEN")


def _assert_runtime_source_is_schema_free() -> None:
    for relative_path in (
        "app/services/password_reset_service.py",
        "app/api/password_reset_routes.py",
    ):
        source = (BACKEND_ROOT / relative_path).read_text(encoding="utf-8").upper()
        for forbidden in (
            "CREATE TABLE",
            "ALTER TABLE",
            "DROP TABLE",
            "CREATE INDEX",
            "DROP INDEX",
        ):
            if forbidden in source:
                raise AssertionError(
                    f"Password-reset runtime source contains schema mutation: {relative_path}: {forbidden}"
                )
    print("POSTGRESQL_PASSWORD_RESET_RUNTIME_DDL_ABSENT_GREEN")


def _insert_user(conn, now: datetime) -> str:
    columns = inspect(conn).get_columns("app_users")
    encoded = hash_password(OLD_PASSWORD)
    known_values = {
        "id": USER_ID,
        "email": USER_EMAIL,
        "password": encoded,
        "password_hash": encoded,
        "account_status": "active",
        "suspended_at": None,
        "created_at": now,
        "updated_at": now,
    }
    required_without_default = {
        str(column.get("name") or "")
        for column in columns
        if not bool(column.get("nullable")) and column.get("default") is None
    }
    unknown_required = required_without_default - set(known_values)
    if unknown_required:
        raise AssertionError(
            "Password-reset fixture mist vereiste app_users-kolommen: "
            f"{sorted(unknown_required)}"
        )
    names = [
        str(column.get("name") or "")
        for column in columns
        if str(column.get("name") or "") in known_values
    ]
    conn.execute(
        text(
            f"INSERT INTO app_users ({', '.join(names)}) "
            f"VALUES ({', '.join(':' + name for name in names)})"
        ),
        {name: known_values[name] for name in names},
    )
    return encoded


def _cleanup(conn) -> None:
    conn.execute(
        text("DELETE FROM account_password_reset_tokens WHERE user_id = :user_id"),
        {"user_id": USER_ID},
    )
    conn.execute(
        text("DELETE FROM server_sessions WHERE user_id = :user_id"),
        {"user_id": USER_ID},
    )
    conn.execute(
        text("DELETE FROM app_users WHERE id = :user_id"),
        {"user_id": USER_ID},
    )


def _exercise_password_reset() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with engine.begin() as conn:
        validate_password_reset_schema(conn)
        _cleanup(conn)
        old_hash = _insert_user(conn, now)
        conn.execute(
            text(
                """
                INSERT INTO server_sessions (
                    id, session_token_hash, user_id, active_household_id,
                    issued_at, expires_at, session_version, revoked_at,
                    replaced_by_session_id, created_at, updated_at
                ) VALUES (
                    :id, :token_hash, :user_id, NULL,
                    :issued_at, :expires_at, 1, NULL,
                    NULL, :issued_at, :issued_at
                )
                """
            ),
            {
                "id": SESSION_ID,
                "token_hash": "8" * 64,
                "user_id": USER_ID,
                "issued_at": now,
                "expires_at": now + timedelta(hours=2),
            },
        )

        request_result = request_password_reset(
            conn,
            email=USER_EMAIL,
            client_ip=CLIENT_IP,
            now=now,
        )
        if not request_result.raw_token or not request_result.token_hash:
            raise AssertionError(f"Reset request did not create token: {request_result}")
        stored = conn.execute(
            text(
                """
                SELECT token_hash, request_ip_hash
                FROM account_password_reset_tokens
                WHERE user_id = :user_id
                """
            ),
            {"user_id": USER_ID},
        ).mappings().one()
        if stored["token_hash"] != request_result.token_hash:
            raise AssertionError("Stored reset token hash does not match request result")
        if request_result.raw_token in str(stored):
            raise AssertionError("Raw reset token leaked into PostgreSQL")
        if stored["request_ip_hash"] == CLIENT_IP:
            raise AssertionError("Raw request IP leaked into PostgreSQL")

        confirm_result = confirm_password_reset(
            conn,
            raw_token=request_result.raw_token,
            new_password=NEW_PASSWORD,
            now=now + timedelta(minutes=1),
        )
        if confirm_result.revoked_sessions != 1:
            raise AssertionError(f"Password reset did not revoke active session: {confirm_result}")

        account = conn.execute(
            text("SELECT password, password_hash FROM app_users WHERE id = :user_id"),
            {"user_id": USER_ID},
        ).mappings().one()
        if account["password"] == old_hash:
            raise AssertionError("Password reset did not replace password hash")
        if account["password"] != account["password_hash"]:
            raise AssertionError("Password and password_hash transition columns diverged")
        if not verify_password(account["password"], NEW_PASSWORD):
            raise AssertionError("New password cannot be verified")

        active_session_count = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM server_sessions
                    WHERE user_id = :user_id AND revoked_at IS NULL
                    """
                ),
                {"user_id": USER_ID},
            ).scalar_one()
        )
        if active_session_count != 0:
            raise AssertionError("Password reset left an active server session")

        token_state = conn.execute(
            text(
                """
                SELECT used_at, revoked_at
                FROM account_password_reset_tokens
                WHERE token_hash = :token_hash
                """
            ),
            {"token_hash": request_result.token_hash},
        ).mappings().one()
        if token_state["used_at"] is None or token_state["revoked_at"] is not None:
            raise AssertionError(f"Consumed token state is invalid: {token_state}")

        _cleanup(conn)

    print("POSTGRESQL_PASSWORD_RESET_DML_ONLY_GREEN")


def main() -> None:
    _assert_runtime_source_is_schema_free()
    _assert_runtime_context()
    _exercise_password_reset()
    print("POSTGRESQL_PASSWORD_RESET_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
