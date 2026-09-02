"""Security contract for forgotten-password recovery on migration-owned schema.

The test performs DML only against the database configured by DATABASE_URL.
Schema creation and ownership remain exclusively with Alembic. In normal
PostgreSQL CI this therefore proves the security lifecycle on canonical schema;
in the explicit SQLite migration-compatibility job it exercises the same DML
contract on the already migrated compatibility database without creating any
SQLite test infrastructure itself.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
import uuid

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import inspect, text

from app.db import engine
from app.services.password_reset_service import (
    PASSWORD_RESET_EMAIL_LIMIT,
    PasswordResetTokenInvalidError,
    confirm_password_reset,
    hash_password_reset_token,
    issue_password_reset,
    validate_password_reset_schema,
)
from app.services.password_service import hash_password, is_password_hash, verify_password


def _expect_invalid(fn) -> None:
    try:
        fn()
    except PasswordResetTokenInvalidError:
        return
    raise AssertionError("Ongeldige/verlopen/hergebruikte reset-token werd geaccepteerd")


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


def _session_insert(
    conn,
    *,
    session_id: str,
    token_hash: str,
    user_id: str,
    now: datetime,
) -> None:
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


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def run() -> int:
    checks: list[str] = []
    now = datetime.now(timezone.utc)
    suffix = uuid.uuid4().hex
    consumer_user_id = f"pr-sec-c-{suffix}"
    other_user_id = f"pr-sec-o-{suffix}"
    consumer_email = f"password-reset-security-{suffix}@example.invalid"
    other_email = f"password-reset-security-other-{suffix}@example.invalid"
    unknown_email = f"password-reset-security-unknown-{suffix}@example.invalid"
    original_password = "OrigineelSterkWachtwoord123!"
    other_password = "AnderSterkWachtwoord123!"
    new_password = "NieuwSterkWachtwoord456!"
    session_ids = [
        f"pr-sec-{suffix[:20]}-a",
        f"pr-sec-{suffix[:20]}-b",
        f"pr-sec-{suffix[:20]}-other",
    ]
    cleanup_hashes = [_email_hash(consumer_email), _email_hash(other_email), _email_hash(unknown_email)]

    try:
        with engine.begin() as conn:
            validate_password_reset_schema(conn)
            _user_insert(
                conn,
                user_id=consumer_user_id,
                email=consumer_email,
                password=original_password,
            )
            _user_insert(
                conn,
                user_id=other_user_id,
                email=other_email,
                password=other_password,
            )
            _session_insert(
                conn,
                session_id=session_ids[0],
                token_hash=uuid.uuid4().hex * 2,
                user_id=consumer_user_id,
                now=now - timedelta(minutes=10),
            )
            _session_insert(
                conn,
                session_id=session_ids[1],
                token_hash=uuid.uuid4().hex * 2,
                user_id=consumer_user_id,
                now=now - timedelta(minutes=10),
            )
            _session_insert(
                conn,
                session_id=session_ids[2],
                token_hash=uuid.uuid4().hex * 2,
                user_id=other_user_id,
                now=now - timedelta(minutes=10),
            )

        with engine.begin() as conn:
            first = issue_password_reset(
                conn,
                email=f"  {consumer_email.upper()}  ",
                request_ip="203.0.113.10",
                now=now,
            )
            assert first.should_deliver
            assert first.raw_token
            assert first.email == consumer_email
            stored = conn.execute(
                text("""
                    SELECT token_hash, request_email_hash, request_ip_hash
                    FROM account_password_reset_tokens
                    WHERE user_id = :user_id
                """),
                {"user_id": consumer_user_id},
            ).mappings().one()
            assert stored["token_hash"] == hash_password_reset_token(first.raw_token)
            assert stored["token_hash"] != first.raw_token
            assert len(stored["request_email_hash"]) == 64
            assert len(stored["request_ip_hash"]) == 64
        checks.append("raw_reset_token_never_persisted")
        checks.append("email_and_ip_rate_dimensions_are_hashed")

        with engine.begin() as conn:
            second = issue_password_reset(
                conn,
                email=consumer_email,
                request_ip="203.0.113.10",
                now=now + timedelta(seconds=5),
            )
            assert second.should_deliver and second.raw_token
            invalidated = conn.execute(
                text("""
                    SELECT invalidated_at
                    FROM account_password_reset_tokens
                    WHERE token_hash = :token_hash
                """),
                {"token_hash": hash_password_reset_token(first.raw_token)},
            ).scalar_one()
            assert invalidated is not None
            _expect_invalid(
                lambda: confirm_password_reset(
                    conn,
                    raw_token=first.raw_token,
                    new_password=new_password,
                    now=now + timedelta(seconds=10),
                )
            )
        checks.append("new_request_invalidates_previous_token")

        with engine.begin() as conn:
            result = confirm_password_reset(
                conn,
                raw_token=second.raw_token,
                new_password=new_password,
                now=now + timedelta(seconds=15),
            )
            assert result.user_id == consumer_user_id
            assert result.revoked_sessions == 2

            user_columns = {item["name"] for item in inspect(conn).get_columns("app_users")}
            selected = "password, password_hash" if "password_hash" in user_columns else "password"
            account = conn.execute(
                text(f"SELECT {selected} FROM app_users WHERE id = :user_id"),
                {"user_id": consumer_user_id},
            ).mappings().one()
            stored_password_hash = account.get("password_hash") if "password_hash" in account else None
            assert is_password_hash(account["password"])
            if stored_password_hash is not None:
                assert stored_password_hash == account["password"]
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

            sessions = {
                row["id"]: row["revoked_at"]
                for row in conn.execute(
                    text("SELECT id, revoked_at FROM server_sessions WHERE id IN (:a, :b, :other)"),
                    {"a": session_ids[0], "b": session_ids[1], "other": session_ids[2]},
                ).mappings().all()
            }
            assert sessions[session_ids[0]] is not None
            assert sessions[session_ids[1]] is not None
            assert sessions[session_ids[2]] is None
        checks.append("confirmed_reset_uses_canonical_password_hash")
        checks.append("confirmed_reset_revokes_all_user_sessions")
        checks.append("other_user_sessions_remain_valid")

        with engine.begin() as conn:
            _expect_invalid(
                lambda: confirm_password_reset(
                    conn,
                    raw_token=second.raw_token,
                    new_password="NogEenSterkWachtwoord789!",
                    now=now + timedelta(seconds=20),
                )
            )
        checks.append("reset_token_is_single_use")

        with engine.begin() as conn:
            unknown = issue_password_reset(
                conn,
                email=unknown_email,
                request_ip="203.0.113.20",
                now=now,
            )
            assert not unknown.should_deliver
            ledger = conn.execute(
                text("""
                    SELECT user_id, token_hash
                    FROM account_password_reset_tokens
                    WHERE request_email_hash = :email_hash
                """),
                {"email_hash": _email_hash(unknown_email)},
            ).mappings().one()
            assert ledger["user_id"] is None
            assert ledger["token_hash"] is None
        checks.append("unknown_account_gets_no_secret_token")

        with engine.begin() as conn:
            # The first unknown request above counts toward the same 15-minute window.
            for offset in range(1, PASSWORD_RESET_EMAIL_LIMIT):
                attempt = issue_password_reset(
                    conn,
                    email=unknown_email,
                    request_ip=f"203.0.113.{20 + offset}",
                    now=now + timedelta(seconds=offset),
                )
                assert not attempt.rate_limited
            limited = issue_password_reset(
                conn,
                email=unknown_email,
                request_ip="203.0.113.99",
                now=now + timedelta(seconds=30),
            )
            assert limited.rate_limited
            assert not limited.should_deliver
        checks.append("email_rate_limit_is_persistent_and_enumeration_safe")

        with engine.begin() as conn:
            expiring = issue_password_reset(
                conn,
                email=other_email,
                request_ip="203.0.113.30",
                now=now,
            )
            assert expiring.raw_token
            _expect_invalid(
                lambda: confirm_password_reset(
                    conn,
                    raw_token=expiring.raw_token,
                    new_password="VerlopenLinkWachtwoord123!",
                    now=now + timedelta(minutes=31),
                )
            )
        checks.append("reset_token_expires_after_thirty_minutes")
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM server_sessions WHERE user_id IN (:consumer, :other)"),
                {"consumer": consumer_user_id, "other": other_user_id},
            )
            conn.execute(
                text("""
                    DELETE FROM account_password_reset_tokens
                    WHERE user_id IN (:consumer, :other)
                       OR request_email_hash IN (:consumer_hash, :other_hash, :unknown_hash)
                """),
                {
                    "consumer": consumer_user_id,
                    "other": other_user_id,
                    "consumer_hash": cleanup_hashes[0],
                    "other_hash": cleanup_hashes[1],
                    "unknown_hash": cleanup_hashes[2],
                },
            )
            conn.execute(
                text("DELETE FROM app_users WHERE id IN (:consumer, :other)"),
                {"consumer": consumer_user_id, "other": other_user_id},
            )

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("PASSWORD_RESET_SECURITY_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
