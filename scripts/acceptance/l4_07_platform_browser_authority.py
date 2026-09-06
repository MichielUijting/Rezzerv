from __future__ import annotations

import os
import sys

from sqlalchemy import text

from app.db import engine
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.testing.postgresql_onboarding_selftest_fixture import seed_user


def required(name: str) -> str:
    value = str(os.environ.get(name, "")).strip()
    if not value:
        raise AssertionError(f"{name} ontbreekt voor L4-07")
    return value


def prove_runtime_boundary() -> None:
    assert engine.dialect.name == "postgresql", engine.dialect.name
    with engine.begin() as conn:
        current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
        runtime_create = bool(
            conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()
        )
    assert current_user == "rezzerv_app", current_user
    assert runtime_create is False


def setup_platform_admin() -> int:
    prove_runtime_boundary()
    platform_user_id = required("L4_PLATFORM_USER_ID")
    platform_email = required("L4_PLATFORM_EMAIL").lower()
    platform_password = required("L4_PLATFORM_PASSWORD")

    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        duplicate = int(
            conn.execute(
                text("SELECT COUNT(*) FROM app_users WHERE lower(email) = :email"),
                {"email": platform_email},
            ).scalar_one()
        )
        assert duplicate == 0, (platform_email, duplicate)
        seed_user(
            conn,
            user_id=platform_user_id,
            email=platform_email,
            password=platform_password,
        )
        conn.execute(
            text(
                """
                INSERT INTO auth_platform_user_roles (user_id, role_key, active)
                VALUES (:user_id, 'platform.platform_admin', TRUE)
                """
            ),
            {"user_id": platform_user_id},
        )
        memberships = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM household_memberships hm
                    JOIN app_users u ON lower(trim(hm.user_email)) = lower(trim(u.email))
                    WHERE u.id = :user_id
                    """
                ),
                {"user_id": platform_user_id},
            ).scalar_one()
        )
        assert memberships == 0

    print(f"platform_user_id={platform_user_id}")
    print(f"platform_email={platform_email}")
    print("P0_L4_07_PLATFORM_FIXTURE_GREEN")
    print("P0_L4_07_POSTGRESQL_BOUNDARY_GREEN")
    return 0


def verify_end_state() -> int:
    prove_runtime_boundary()
    platform_user_id = required("L4_PLATFORM_USER_ID")
    platform_email = required("L4_PLATFORM_EMAIL").lower()
    target_email = required("L4_TARGET_EMAIL").lower()
    target_household_id = required("L4_TARGET_HOUSEHOLD_ID")
    revoked_session_id = required("L4_REVOKED_SESSION_ID")

    with engine.begin() as conn:
        platform_user = conn.execute(
            text("SELECT id, email FROM app_users WHERE id = :user_id"),
            {"user_id": platform_user_id},
        ).mappings().one()
        assert str(platform_user["email"]).lower() == platform_email, platform_user

        platform_role_count = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM auth_platform_user_roles
                    WHERE user_id = :user_id
                      AND role_key = 'platform.platform_admin'
                      AND active IS TRUE
                    """
                ),
                {"user_id": platform_user_id},
            ).scalar_one()
        )
        assert platform_role_count == 1

        platform_membership_count = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM household_memberships hm
                    JOIN app_users u ON lower(trim(hm.user_email)) = lower(trim(u.email))
                    WHERE u.id = :user_id
                    """
                ),
                {"user_id": platform_user_id},
            ).scalar_one()
        )
        assert platform_membership_count == 0

        target_user = conn.execute(
            text("SELECT id, email FROM app_users WHERE lower(email) = :email"),
            {"email": target_email},
        ).mappings().one()
        target_user_id = str(target_user["id"])

        target_memberships = conn.execute(
            text(
                """
                SELECT hm.household_id, hm.role
                FROM household_memberships hm
                WHERE lower(trim(hm.user_email)) = :email
                ORDER BY hm.household_id
                """
            ),
            {"email": target_email},
        ).mappings().all()
        assert len(target_memberships) == 1, target_memberships
        assert str(target_memberships[0]["household_id"]) == target_household_id, target_memberships
        assert str(target_memberships[0]["role"]) == "admin", target_memberships

        revoked_session = conn.execute(
            text(
                """
                SELECT id, user_id, revoked_at, expires_at
                FROM server_sessions
                WHERE id = :session_id
                """
            ),
            {"session_id": revoked_session_id},
        ).mappings().one()
        assert str(revoked_session["user_id"]) == target_user_id, revoked_session
        assert revoked_session["revoked_at"] is not None, revoked_session

        active_platform_sessions = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM server_sessions
                    WHERE user_id = :user_id
                      AND revoked_at IS NULL
                      AND expires_at > CURRENT_TIMESTAMP
                    """
                ),
                {"user_id": platform_user_id},
            ).scalar_one()
        )
        assert active_platform_sessions >= 1

        target_platform_roles = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM auth_platform_user_roles
                    WHERE user_id = :target_user_id
                      AND active IS TRUE
                    """
                ),
                {"target_user_id": target_user_id},
            ).scalar_one()
        )
        assert target_platform_roles == 0

        household = conn.execute(
            text("SELECT id, context_type FROM household_registry WHERE id = :household_id"),
            {"household_id": target_household_id},
        ).mappings().one()
        assert str(household["context_type"]) == "regular", household

    print(f"platform_user_id={platform_user_id}")
    print(f"target_user_id={target_user_id}")
    print(f"target_household_id={target_household_id}")
    print(f"revoked_session_id={revoked_session_id}")
    print("P0_L4_07_PLATFORM_ROLE_WITHOUT_HOUSEHOLD_MEMBERSHIP_GREEN")
    print("P0_L4_07_TARGET_SESSION_REVOKED_GREEN")
    print("P0_L4_07_PLATFORM_SESSION_REMAINS_ACTIVE_GREEN")
    print("P0_L4_07_POSTGRESQL_END_STATE_GREEN")
    return 0


def main() -> int:
    mode = str(sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode == "setup":
        return setup_platform_admin()
    if mode == "verify":
        return verify_end_state()
    raise SystemExit("Gebruik: l4_07_platform_browser_authority.py setup|verify")


if __name__ == "__main__":
    raise SystemExit(main())
