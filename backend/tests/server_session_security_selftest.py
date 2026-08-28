"""Self-contained Rezzerv server-session security validation.

Runs with the standard backend Python runtime. No pytest dependency.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import tempfile

from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.server_session_service import (
    create_server_session,
    create_system_server_session,
    resolve_server_session,
    revoke_server_session,
)
from app.services.system_superuser_session_provisioning import (
    SUPERGEBRUIKER_EMAIL,
    SUPERGEBRUIKER_HUISHOUDEN_ID,
)
from app.testing.server_session_contract import create_server_session_contract_schema


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
        conn.execute(text(
            "CREATE TABLE household_registry ("
            "id TEXT PRIMARY KEY, context_type TEXT NOT NULL)"
        ))
        conn.execute(text(
            "INSERT INTO household_registry(id, context_type) VALUES "
            "('0', 'system'), ('1', 'regular'), ('2', 'regular')"
        ))
        conn.execute(text("CREATE TABLE app_users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE)"))
        conn.execute(text(
            "CREATE TABLE household_memberships ("
            "user_id TEXT NOT NULL, household_id TEXT NOT NULL, role TEXT NOT NULL, "
            "PRIMARY KEY (user_id, household_id))"
        ))
        conn.execute(text(
            "INSERT INTO app_users (id, email) VALUES "
            "('user-a', 'a@rezzerv.local'), "
            "('user-b', 'b@rezzerv.local'), "
            "('system-superuser', 'supergebruiker@rezzerv.local')"
        ))
        conn.execute(text(
            "INSERT INTO household_memberships (user_id, household_id, role) VALUES "
            "('user-a', '1', 'owner'), "
            "('user-b', '2', 'member')"
        ))
        ensure_authorization_foundation(conn)
        conn.execute(text(
            "INSERT INTO auth_membership_roles "
            "(household_id, membership_id, role_key, active) VALUES "
            "('1', 'user-a', 'household.admin', 1), "
            "('2', 'user-b', 'household.member', 1)"
        ))
        conn.execute(text(
            "INSERT INTO auth_platform_user_roles(user_id, role_key, active) "
            "VALUES ('system-superuser', 'platform.superuser', 1)"
        ))
        create_server_session_contract_schema(conn)


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
            assert context.context_type == "regular"
            assert context.role == "admin"
        checks.append("valid_session_created")

        with engine.begin() as conn:
            resolved = resolve_server_session(conn, raw_session)
            assert resolved.email == "a@rezzerv.local"
            assert resolved.active_household_id == "1"
            assert resolved.role == "admin"
        checks.append("valid_session_resolved")

        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE household_memberships SET role = 'viewer' "
                "WHERE user_id = 'user-a' AND household_id = '1'"
            ))
        with engine.begin() as conn:
            resolved = resolve_server_session(conn, raw_session)
            assert resolved.role == "admin"
        checks.append("stale_legacy_role_ignored")

        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE auth_membership_roles SET role_key = 'household.viewer' "
                "WHERE household_id = '1' AND membership_id = 'user-a'"
            ))
        with engine.begin() as conn:
            resolved = resolve_server_session(conn, raw_session)
            assert resolved.role == "viewer"
        checks.append("canonical_role_refreshed_server_side")

        with engine.begin() as conn:
            superuser_session, superuser_context = create_system_server_session(
                conn,
                user_id="system-superuser",
            )
            assert superuser_session
            assert superuser_context.email == SUPERGEBRUIKER_EMAIL
            assert superuser_context.active_household_id == SUPERGEBRUIKER_HUISHOUDEN_ID
            assert superuser_context.context_type == "system"
            assert superuser_context.role == "owner"
            assert superuser_context.is_platform_superuser is True
            assert conn.execute(text(
                "SELECT COUNT(*) FROM household_memberships "
                "WHERE user_id = 'system-superuser'"
            )).scalar_one() == 0
        with engine.begin() as conn:
            resolved_superuser = resolve_server_session(conn, superuser_session)
            assert resolved_superuser.email == SUPERGEBRUIKER_EMAIL
            assert resolved_superuser.active_household_id == SUPERGEBRUIKER_HUISHOUDEN_ID
            assert resolved_superuser.is_platform_superuser is True
        checks.append("platform_role_superuser_system_context_allowed")

        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE auth_platform_user_roles SET active = 0 "
                "WHERE user_id = 'system-superuser' AND role_key = 'platform.superuser'"
            ))
        with engine.begin() as conn:
            _expect_http_status(
                403,
                lambda: resolve_server_session(conn, superuser_session),
            )
            _expect_http_status(
                403,
                lambda: create_system_server_session(
                    conn,
                    user_id="system-superuser",
                ),
            )
        checks.append("inactive_superuser_role_blocks_system_context")

        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO household_memberships (user_id, household_id, role) "
                "VALUES ('user-a', '0', 'owner')"
            ))
            _expect_http_status(
                403,
                lambda: create_server_session(
                    conn,
                    user_id="user-a",
                    active_household_id="0",
                ),
            )
        checks.append("household_zero_blocked_for_regular_user")

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
