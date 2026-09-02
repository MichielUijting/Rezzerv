"""Prove forgotten-password recovery works with the DML-only PostgreSQL runtime role."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import inspect, text

from app.db import engine
from app.services.password_reset_service import (
    confirm_password_reset,
    hash_password_reset_token,
    issue_password_reset,
    validate_password_reset_schema,
)
from app.services.password_service import hash_password, verify_password


def _user_insert(conn, *, user_id: str, email: str, password: str) -> None:
    columns = {item["name"] for item in inspect(conn).get_columns("app_users")}
    encoded = hash_password(password)
    names = ["id", "email", "password"]
    values = [":id", ":email", ":password"]
    params = {"id": user_id, "email": email, "password": encoded}
    if "password_hash" in columns:
        names.append("password_hash")
        values.append(":password_hash")
        params["password_hash"] = encoded
    if "account_status" in columns:
        names.append("account_status")
        values.append("'active'")
    if "created_at" in columns:
        names.append("created_at")
        values.append("CURRENT_TIMESTAMP")
    if "updated_at" in columns:
        names.append("updated_at")
        values.append("CURRENT_TIMESTAMP")
    conn.execute(
        text(f"INSERT INTO app_users ({', '.join(names)}) VALUES ({', '.join(values)})"),
        params,
    )


def _session_insert(conn, *, session_id: str, token_hash: str, user_id: str, now: datetime) -> None:
    conn.execute(
        text("""
            INSERT INTO server_sessions(
                id, session_token_hash, user_id, active_household_id,
                issued_at, expires_at, session_version, revoked_at,
                replaced_by_session_id, created_at, updated_at
            ) VALUES (
                :id, :token_hash, :user_id, NULL,
                :issued_at, :expires_at, 1, NULL,
                NULL, :issued_at, :issued_at
            )
        """),
        {
            "id": session_id,
            "token_hash": token_hash,
            "user_id": user_id,
            "issued_at": now,
            "expires_at": now + timedelta(hours=1),
        },
    )


def run() -> int:
    if engine.dialect.name != "postgresql":
        raise AssertionError(f"PostgreSQL required, got {engine.dialect.name}")

    suffix = uuid.uuid4().hex
    user_id = f"password-reset-dml-{suffix}"
    email = f"password-reset-{suffix}@example.invalid"
    original_password = "OrigineelSterkWachtwoord123!"
    new_password = "NieuwSterkWachtwoord456!"
    now = datetime.now(timezone.utc)
    session_ids = [f"pr-{suffix[:20]}-a", f"pr-{suffix[:20]}-b"]

    try:
        with engine.begin() as conn:
            current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
            can_create = bool(
                conn.execute(
                    text("SELECT has_schema_privilege(current_user, current_schema(), 'CREATE')")
                ).scalar_one()
            )
            assert not can_create, f"Runtime role {current_user} unexpectedly has CREATE"
            print("POSTGRESQL_PASSWORD_RESET_RUNTIME_CREATE_DENIED_GREEN")

            validate_password_reset_schema(conn)
            _user_insert(
                conn,
                user_id=user_id,
                email=email,
                password=original_password,
            )
            _session_insert(
                conn,
                session_id=session_ids[0],
                token_hash=uuid.uuid4().hex * 2,
                user_id=user_id,
                now=now,
            )
            _session_insert(
                conn,
                session_id=session_ids[1],
                token_hash=uuid.uuid4().hex * 2,
                user_id=user_id,
                now=now,
            )

            issued = issue_password_reset(
                conn,
                email=email,
                request_ip="127.0.0.1",
                now=now,
            )
            assert issued.should_deliver and issued.raw_token
            stored_hash = conn.execute(
                text("""
                    SELECT token_hash
                    FROM account_password_reset_tokens
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id},
            ).scalar_one()
            assert stored_hash == hash_password_reset_token(issued.raw_token)
            assert stored_hash != issued.raw_token
            print("POSTGRESQL_PASSWORD_RESET_HASHED_TOKEN_GREEN")

            confirmed = confirm_password_reset(
                conn,
                raw_token=issued.raw_token,
                new_password=new_password,
                now=now + timedelta(seconds=1),
            )
            assert confirmed.user_id == user_id
            assert confirmed.revoked_sessions == 2

            user_columns = {item["name"] for item in inspect(conn).get_columns("app_users")}
            selected = "password, password_hash" if "password_hash" in user_columns else "password"
            account = conn.execute(
                text(f"SELECT {selected} FROM app_users WHERE id = :user_id"),
                {"user_id": user_id},
            ).mappings().one()
            stored_password_hash = account.get("password_hash") if "password_hash" in account else None
            assert verify_password(
                account["password"],
                new_password,
                stored_password_hash=stored_password_hash,
            )
            assert not verify_password(
                account["password"],
                original_password,
                stored_password_hash=stored_password_hash,
            )
            revoked = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM server_sessions
                    WHERE user_id = :user_id AND revoked_at IS NOT NULL
                """),
                {"user_id": user_id},
            ).scalar_one()
            assert int(revoked) == 2
            print("POSTGRESQL_PASSWORD_RESET_ALL_SESSIONS_REVOKED_GREEN")
            print("POSTGRESQL_PASSWORD_RESET_DML_ONLY_GREEN")
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM server_sessions WHERE user_id = :user_id"), {"user_id": user_id})
            conn.execute(text("DELETE FROM account_password_reset_tokens WHERE user_id = :user_id"), {"user_id": user_id})
            conn.execute(text("DELETE FROM app_users WHERE id = :user_id"), {"user_id": user_id})

    print("POSTGRESQL_PASSWORD_RESET_AUTHORITY_SELFTEST_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
