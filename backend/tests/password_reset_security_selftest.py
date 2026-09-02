"""Security contract for forgotten-password recovery.

This service-level test is deliberately self-contained. Alembic ownership and
PostgreSQL type/index authority are covered by migration_foundation_head_selftest.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine, text

from app.services.password_reset_service import (
    PASSWORD_RESET_EMAIL_LIMIT,
    PasswordResetTokenInvalidError,
    confirm_password_reset,
    hash_password_reset_token,
    issue_password_reset,
)
from app.services.password_service import is_password_hash, verify_password
from app.testing.server_session_contract import create_server_session_contract_schema


def _expect_invalid(fn) -> None:
    try:
        fn()
    except PasswordResetTokenInvalidError:
        return
    raise AssertionError("Ongeldige/verlopen/hergebruikte reset-token werd geaccepteerd")


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
        conn.execute(text("""
            CREATE TABLE account_password_reset_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NULL,
                request_email_hash TEXT NOT NULL,
                request_ip_hash TEXT NOT NULL,
                token_hash TEXT NULL UNIQUE,
                requested_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NULL,
                used_at TIMESTAMP NULL,
                invalidated_at TIMESTAMP NULL,
                FOREIGN KEY(user_id) REFERENCES app_users(id) ON DELETE CASCADE
            )
        """))

        issued_at = now - timedelta(minutes=10)
        expires_at = now + timedelta(hours=1)
        rows = [
            ('session-current', 'a' * 64, 'consumer-user'),
            ('session-other', 'b' * 64, 'consumer-user'),
            ('session-other-user', 'c' * 64, 'other-user'),
        ]
        for session_id, token_hash, user_id in rows:
            conn.execute(text("""
                INSERT INTO server_sessions(
                    id, session_token_hash, user_id, active_household_id,
                    issued_at, expires_at, session_version, revoked_at,
                    replaced_by_session_id, created_at, updated_at
                ) VALUES (
                    :id, :token_hash, :user_id, NULL,
                    :issued_at, :expires_at, 1, NULL,
                    NULL, :issued_at, :issued_at
                )
            """), {
                "id": session_id,
                "token_hash": token_hash,
                "user_id": user_id,
                "issued_at": issued_at,
                "expires_at": expires_at,
            })


def run() -> int:
    checks: list[str] = []
    now = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)

    with tempfile.TemporaryDirectory(prefix="rezzerv-password-reset-") as tmp:
        engine = create_engine(f"sqlite:///{Path(tmp) / 'password-reset.db'}", future=True)
        _prepare_database(engine, now)

        with engine.begin() as conn:
            first = issue_password_reset(
                conn,
                email=" Consumer@Example.com ",
                request_ip="203.0.113.10",
                now=now,
            )
            assert first.should_deliver
            assert first.raw_token
            assert first.email == "consumer@example.com"
            stored = conn.execute(text("""
                SELECT token_hash, request_email_hash, request_ip_hash
                FROM account_password_reset_tokens
                WHERE user_id = 'consumer-user'
            """)).mappings().one()
            assert stored["token_hash"] == hash_password_reset_token(first.raw_token)
            assert stored["token_hash"] != first.raw_token
            assert len(stored["request_email_hash"]) == 64
            assert len(stored["request_ip_hash"]) == 64
        checks.append("raw_reset_token_never_persisted")
        checks.append("email_and_ip_rate_dimensions_are_hashed")

        with engine.begin() as conn:
            second = issue_password_reset(
                conn,
                email="consumer@example.com",
                request_ip="203.0.113.10",
                now=now + timedelta(seconds=5),
            )
            assert second.should_deliver and second.raw_token
            invalidated = conn.execute(text("""
                SELECT invalidated_at
                FROM account_password_reset_tokens
                WHERE token_hash = :token_hash
            """), {"token_hash": hash_password_reset_token(first.raw_token)}).scalar_one()
            assert invalidated is not None
            _expect_invalid(lambda: confirm_password_reset(
                conn,
                raw_token=first.raw_token,
                new_password="NieuwSterkWachtwoord456!",
                now=now + timedelta(seconds=10),
            ))
        checks.append("new_request_invalidates_previous_token")

        with engine.begin() as conn:
            result = confirm_password_reset(
                conn,
                raw_token=second.raw_token,
                new_password="NieuwSterkWachtwoord456!",
                now=now + timedelta(seconds=15),
            )
            assert result.user_id == "consumer-user"
            assert result.revoked_sessions == 2

            account = conn.execute(text("""
                SELECT password, password_hash FROM app_users WHERE id = 'consumer-user'
            """)).mappings().one()
            assert is_password_hash(account["password"])
            assert account["password_hash"] == account["password"]
            assert verify_password(
                account["password"],
                "NieuwSterkWachtwoord456!",
                stored_password_hash=account["password_hash"],
            )
            assert not verify_password(
                account["password"],
                "LegacyPass123!",
                stored_password_hash=account["password_hash"],
            )

            sessions = {
                row["id"]: row["revoked_at"]
                for row in conn.execute(text("""
                    SELECT id, revoked_at FROM server_sessions ORDER BY id
                """)).mappings().all()
            }
            assert sessions["session-current"] is not None
            assert sessions["session-other"] is not None
            assert sessions["session-other-user"] is None
        checks.append("confirmed_reset_uses_canonical_password_hash")
        checks.append("confirmed_reset_revokes_all_user_sessions")
        checks.append("other_user_sessions_remain_valid")

        with engine.begin() as conn:
            _expect_invalid(lambda: confirm_password_reset(
                conn,
                raw_token=second.raw_token,
                new_password="NogEenSterkWachtwoord789!",
                now=now + timedelta(seconds=20),
            ))
        checks.append("reset_token_is_single_use")

        with engine.begin() as conn:
            unknown = issue_password_reset(
                conn,
                email="unknown@example.com",
                request_ip="203.0.113.20",
                now=now,
            )
            assert not unknown.should_deliver
            ledger = conn.execute(text("""
                SELECT user_id, token_hash
                FROM account_password_reset_tokens
                WHERE request_email_hash = :email_hash
            """), {
                "email_hash": __import__('hashlib').sha256(b'unknown@example.com').hexdigest()
            }).mappings().one()
            assert ledger["user_id"] is None
            assert ledger["token_hash"] is None
        checks.append("unknown_account_gets_no_secret_token")

        with engine.begin() as conn:
            # The first unknown request above counts toward the same 15-minute window.
            for offset in range(1, PASSWORD_RESET_EMAIL_LIMIT):
                attempt = issue_password_reset(
                    conn,
                    email="unknown@example.com",
                    request_ip=f"203.0.113.{20 + offset}",
                    now=now + timedelta(seconds=offset),
                )
                assert not attempt.rate_limited
            limited = issue_password_reset(
                conn,
                email="unknown@example.com",
                request_ip="203.0.113.99",
                now=now + timedelta(seconds=30),
            )
            assert limited.rate_limited
            assert not limited.should_deliver
        checks.append("email_rate_limit_is_persistent_and_enumeration_safe")

        with engine.begin() as conn:
            expiring = issue_password_reset(
                conn,
                email="other@example.com",
                request_ip="203.0.113.30",
                now=now,
            )
            assert expiring.raw_token
            _expect_invalid(lambda: confirm_password_reset(
                conn,
                raw_token=expiring.raw_token,
                new_password="VerlopenLinkWachtwoord123!",
                now=now + timedelta(minutes=31),
            ))
        checks.append("reset_token_expires_after_thirty_minutes")

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("PASSWORD_RESET_SECURITY_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
