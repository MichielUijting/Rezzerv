"""Self-contained Rezzerv server-session security validation.

Runs with the standard backend Python runtime. No pytest dependency.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import tempfile

from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.server_session_service import (
    create_server_session,
    resolve_server_session,
    revoke_server_session,
)


def _expect_http_status(expected_status: int, fn) -> None:
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == expected_status, (
            f"verwacht HTTP {expected_status}, kreeg HTTP {exc.status_code}"
        )
        return
    raise AssertionError(f"verwacht HTTP {expected_status}, maar geen fout ontvangen")


def _prepare_database(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE app_users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE)"))
        conn.execute(text(
            "CREATE TABLE household_memberships ("
            "user_id TEXT NOT NULL, household_id TEXT NOT NULL, role TEXT NOT NULL, "
            "PRIMARY KEY (user_id, household_id))"
        ))
        conn.execute(text(
            "INSERT INTO app_users (id, email) VALUES "
            "('user-a', 'a@rezzerv.local'), ('user-b', 'b@rezzerv.local')"
        ))
        conn.execute(text(
            "INSERT INTO household_memberships (user_id, household_id, role) VALUES "
            "('user-a', '1', 'owner'), ('user-b', '2', 'member')"
        ))


def run() -> int:
    checks = []
    with tempfile.TemporaryDirectory(prefix="rezzerv-session-selftest-") as tmp:
        database_path = Path(tmp) / "session.db"
        engine = create_engine(f"sqlite:///{database_path}", future=True)
        _prepare_database(engine)

        with engine.begin() as conn:
            _expect_http_status(401, lambda: resolve_server_session(conn, None))
        checks.append("missing_cookie_401")

        with engine.begin() as conn:
            raw_session, context = create_server_session(
                conn,
                user_id="user-a",
                active_household_id="1",
                ttl=timedelta(hours=1),
            )
            assert raw_session
            assert context.user_id == "user-a"
            assert context.active_household_id == "1"
            assert context.role == "owner"
        checks.append("valid_session_created")

        with engine.begin() as conn:
            resolved = resolve_server_session(conn, raw_session)
            assert resolved.email == "a@rezzerv.local"
            assert resolved.active_household_id == "1"
            assert resolved.role == "owner"
        checks.append("valid_session_resolved")

        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE household_memberships SET role = 'viewer' "
                "WHERE user_id = 'user-a' AND household_id = '1'"
            ))
        with engine.begin() as conn:
            resolved = resolve_server_session(conn, raw_session)
            assert resolved.role == "viewer"
        checks.append("role_refreshed_server_side")

        with engine.begin() as conn:
            _expect_http_status(
                403,
                lambda: create_server_session(
                    conn,
                    user_id="user-a",
                    active_household_id="0",
                ),
            )
        checks.append("household_zero_blocked")

        with engine.begin() as conn:
            _expect_http_status(
                403,
                lambda: create_server_session(
                    conn,
                    user_id="user-a",
                    active_household_id="2",
                ),
            )
        checks.append("cross_household_membership_blocked")

        with engine.begin() as conn:
            revoke_server_session(conn, raw_session)
        with engine.begin() as conn:
            _expect_http_status(401, lambda: resolve_server_session(conn, raw_session))
        checks.append("revoked_session_401")

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("SERVER_SESSION_SECURITY_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
