"""Self-contained validation for 9.3.3 consumer account management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from pydantic import ValidationError
from sqlalchemy import create_engine, text

from app.api.consumer_account_routes import ConsumerPasswordChangeRequest
from app.services.consumer_account_management_service import (
    ConsumerCurrentPasswordMismatchError,
    ConsumerPasswordReuseError,
    change_consumer_password,
)
from app.services.password_service import is_password_hash, verify_password
from app.testing.server_session_contract import create_server_session_contract_schema


def _expect_error(error_type, fn) -> None:
    try:
        fn()
    except error_type:
        return
    raise AssertionError(f"verwacht {error_type.__name__}, maar geen fout ontvangen")


def _prepare_database(engine, now: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                password_hash TEXT NULL,
                account_status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            INSERT INTO app_users(id, email, password, password_hash, account_status)
            VALUES
                ('consumer-user', 'consumer@example.com', 'LegacyPass123!', NULL, 'active'),
                ('other-user', 'other@example.com', 'OtherLegacyPass123!', NULL, 'active')
        """))
        create_server_session_contract_schema(conn)

        issued_at = now - timedelta(hours=1)
        expires_at = now + timedelta(hours=1)
        expired_at = now - timedelta(minutes=5)
        pre_revoked_at = now - timedelta(minutes=10)
        rows = [
            ('session-current', 'a' * 64, 'consumer-user', issued_at, expires_at, None),
            ('session-other-active', 'b' * 64, 'consumer-user', issued_at, expires_at, None),
            ('session-expired', 'c' * 64, 'consumer-user', issued_at - timedelta(hours=2), expired_at, None),
            ('session-already-revoked', 'd' * 64, 'consumer-user', issued_at, expires_at, pre_revoked_at),
            ('session-other-user', 'e' * 64, 'other-user', issued_at, expires_at, None),
        ]
        for session_id, token_hash, user_id, issued, expires, revoked in rows:
            conn.execute(text("""
                INSERT INTO server_sessions(
                    id, session_token_hash, user_id, active_household_id,
                    issued_at, expires_at, session_version, revoked_at,
                    replaced_by_session_id, created_at, updated_at
                ) VALUES (
                    :id, :token_hash, :user_id, 'household-1',
                    :issued_at, :expires_at, 1, :revoked_at,
                    NULL, :issued_at, :issued_at
                )
            """), {
                "id": session_id,
                "token_hash": token_hash,
                "user_id": user_id,
                "issued_at": issued,
                "expires_at": expires,
                "revoked_at": revoked,
            })


def run() -> int:
    checks: list[str] = []
    now = datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory(prefix="rezzerv-account-management-") as tmp:
        engine = create_engine(f"sqlite:///{Path(tmp) / 'account.db'}", future=True)
        _prepare_database(engine, now)

        try:
            ConsumerPasswordChangeRequest(
                current_password="LegacyPass123!",
                new_password="kort",
            )
        except ValidationError:
            pass
        else:
            raise AssertionError("te kort nieuw wachtwoord werd niet geweigerd")
        checks.append("new_password_policy_matches_registration_minimum")

        with engine.begin() as conn:
            _expect_error(
                ConsumerCurrentPasswordMismatchError,
                lambda: change_consumer_password(
                    conn,
                    user_id="consumer-user",
                    current_session_id="session-current",
                    current_password="VerkeerdWachtwoord123!",
                    new_password="NieuwSterkWachtwoord456!",
                    now=now,
                ),
            )
            password_before = conn.execute(text("""
                SELECT password FROM app_users WHERE id = 'consumer-user'
            """)).scalar_one()
            revoked_before = conn.execute(text("""
                SELECT revoked_at FROM server_sessions WHERE id = 'session-other-active'
            """)).scalar_one_or_none()
            assert password_before == "LegacyPass123!"
            assert revoked_before is None
        checks.append("wrong_current_password_changes_nothing")

        with engine.begin() as conn:
            _expect_error(
                ConsumerPasswordReuseError,
                lambda: change_consumer_password(
                    conn,
                    user_id="consumer-user",
                    current_session_id="session-current",
                    current_password="LegacyPass123!",
                    new_password="LegacyPass123!",
                    now=now,
                ),
            )
        checks.append("password_reuse_rejected")

        with engine.begin() as conn:
            result = change_consumer_password(
                conn,
                user_id="consumer-user",
                current_session_id="session-current",
                current_password="LegacyPass123!",
                new_password="NieuwSterkWachtwoord456!",
                now=now,
            )
            assert result == {
                "password_updated": True,
                "other_active_sessions_revoked": 1,
            }

        with engine.begin() as conn:
            account = conn.execute(text("""
                SELECT password, password_hash
                FROM app_users
                WHERE id = 'consumer-user'
            """)).mappings().one()
            assert is_password_hash(account["password"])
            assert account["password_hash"] == account["password"]
            assert not verify_password(
                account["password"],
                "LegacyPass123!",
                stored_password_hash=account["password_hash"],
            )
            assert verify_password(
                account["password"],
                "NieuwSterkWachtwoord456!",
                stored_password_hash=account["password_hash"],
            )

            sessions = {
                row["id"]: row["revoked_at"]
                for row in conn.execute(text("""
                    SELECT id, revoked_at
                    FROM server_sessions
                    ORDER BY id
                """)).mappings().all()
            }
            assert sessions["session-current"] is None
            assert sessions["session-other-active"] is not None
            assert sessions["session-expired"] is None
            assert sessions["session-already-revoked"] is not None
            assert sessions["session-other-user"] is None
        checks.append("legacy_password_migrated_to_canonical_hash")
        checks.append("only_other_active_sessions_revoked")
        checks.append("current_session_remains_valid")

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("CONSUMER_ACCOUNT_MANAGEMENT_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())