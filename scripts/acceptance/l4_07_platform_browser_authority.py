from __future__ import annotations

import os
import sys

from sqlalchemy import text

from app.db import engine
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.testing.postgresql_onboarding_selftest_fixture import seed_household, seed_user


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


def assign_platform_role(conn, user_id: str, role_key: str) -> None:
    conn.execute(
        text(
            """
            INSERT INTO auth_platform_user_roles (user_id, role_key, active)
            VALUES (:user_id, :role_key, TRUE)
            """
        ),
        {"user_id": user_id, "role_key": role_key},
    )


def assert_no_membership(conn, user_id: str) -> None:
    count = int(
        conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM household_memberships hm
                JOIN app_users u ON lower(trim(hm.user_email)) = lower(trim(u.email))
                WHERE u.id = :user_id
                """
            ),
            {"user_id": user_id},
        ).scalar_one()
    )
    assert count == 0, (user_id, count)


def setup_platform_authority() -> int:
    prove_runtime_boundary()
    identities = (
        (required("L4_PLATFORM_USER_ID"), required("L4_PLATFORM_EMAIL").lower(), required("L4_PLATFORM_PASSWORD"), "platform.platform_admin"),
        (required("L4_SUPERUSER_USER_ID"), required("L4_SUPERUSER_EMAIL").lower(), required("L4_SUPERUSER_PASSWORD"), "platform.superuser"),
        (required("L4_IP_OWNER_USER_ID"), required("L4_IP_OWNER_EMAIL").lower(), required("L4_IP_OWNER_PASSWORD"), "platform.ip_owner"),
    )
    standalone_id = required("L4_STANDALONE_USER_ID")
    standalone_email = required("L4_STANDALONE_EMAIL").lower()
    standalone_password = required("L4_STANDALONE_PASSWORD")

    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        if int(conn.execute(text("SELECT COUNT(*) FROM household_registry WHERE id = '0'")).scalar_one()) == 0:
            seed_household(conn, household_id="0", name="Systeem", context_type="system")

        for user_id, email, password, role_key in identities:
            duplicate = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM app_users WHERE lower(email) = :email"),
                    {"email": email},
                ).scalar_one()
            )
            assert duplicate == 0, (email, duplicate)
            seed_user(conn, user_id=user_id, email=email, password=password)
            assign_platform_role(conn, user_id, role_key)
            assert_no_membership(conn, user_id)

        duplicate = int(
            conn.execute(
                text("SELECT COUNT(*) FROM app_users WHERE lower(email) = :email"),
                {"email": standalone_email},
            ).scalar_one()
        )
        assert duplicate == 0, (standalone_email, duplicate)
        seed_user(conn, user_id=standalone_id, email=standalone_email, password=standalone_password)
        assert_no_membership(conn, standalone_id)
        assert int(
            conn.execute(
                text("SELECT COUNT(*) FROM auth_platform_user_roles WHERE user_id = :user_id AND active IS TRUE"),
                {"user_id": standalone_id},
            ).scalar_one()
        ) == 0

    print(f"platform_user_id={identities[0][0]}")
    print(f"superuser_user_id={identities[1][0]}")
    print(f"ip_owner_user_id={identities[2][0]}")
    print(f"standalone_user_id={standalone_id}")
    print("P0_L4_07_PLATFORM_FIXTURE_GREEN")
    print("P0_L4_07_SUPERUSER_FIXTURE_GREEN")
    print("P0_L4_07_IP_OWNER_FIXTURE_GREEN")
    print("P0_L4_07_POSTGRESQL_BOUNDARY_GREEN")
    return 0


def verify_end_state() -> int:
    prove_runtime_boundary()
    platform_id = required("L4_PLATFORM_USER_ID")
    platform_email = required("L4_PLATFORM_EMAIL").lower()
    superuser_id = required("L4_SUPERUSER_USER_ID")
    superuser_email = required("L4_SUPERUSER_EMAIL").lower()
    ip_owner_id = required("L4_IP_OWNER_USER_ID")
    ip_owner_email = required("L4_IP_OWNER_EMAIL").lower()
    standalone_id = required("L4_STANDALONE_USER_ID")
    standalone_email = required("L4_STANDALONE_EMAIL").lower()
    target_email = required("L4_TARGET_EMAIL").lower()
    target_household_id = required("L4_TARGET_HOUSEHOLD_ID")
    revoked_session_id = required("L4_REVOKED_SESSION_ID")

    with engine.begin() as conn:
        for user_id, email, role_key in (
            (platform_id, platform_email, "platform.platform_admin"),
            (superuser_id, superuser_email, "platform.superuser"),
            (ip_owner_id, ip_owner_email, "platform.ip_owner"),
        ):
            user = conn.execute(
                text("SELECT id, email FROM app_users WHERE id = :user_id"),
                {"user_id": user_id},
            ).mappings().one()
            assert str(user["email"]).lower() == email, user
            assert int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM auth_platform_user_roles
                        WHERE user_id = :user_id AND role_key = :role_key AND active IS TRUE
                        """
                    ),
                    {"user_id": user_id, "role_key": role_key},
                ).scalar_one()
            ) == 1
            assert_no_membership(conn, user_id)

        assert int(
            conn.execute(
                text("SELECT COUNT(*) FROM auth_platform_user_roles WHERE role_key = 'platform.ip_owner' AND active IS TRUE")
            ).scalar_one()
        ) == 1

        target_user = conn.execute(
            text("SELECT id, email FROM app_users WHERE lower(email) = :email"),
            {"email": target_email},
        ).mappings().one()
        target_user_id = str(target_user["id"])
        memberships = conn.execute(
            text(
                """
                SELECT household_id, role FROM household_memberships
                WHERE lower(trim(user_email)) = :email ORDER BY household_id
                """
            ),
            {"email": target_email},
        ).mappings().all()
        assert len(memberships) == 1, memberships
        assert str(memberships[0]["household_id"]) == target_household_id, memberships
        assert str(memberships[0]["role"]) == "admin", memberships

        revoked = conn.execute(
            text("SELECT id, user_id, revoked_at FROM server_sessions WHERE id = :session_id"),
            {"session_id": revoked_session_id},
        ).mappings().one()
        assert str(revoked["user_id"]) == target_user_id, revoked
        assert revoked["revoked_at"] is not None, revoked
        assert int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM server_sessions
                    WHERE user_id = :user_id AND revoked_at IS NULL AND expires_at > CURRENT_TIMESTAMP
                    """
                ),
                {"user_id": platform_id},
            ).scalar_one()
        ) >= 1
        assert int(
            conn.execute(
                text("SELECT COUNT(*) FROM auth_platform_user_roles WHERE user_id = :user_id AND active IS TRUE"),
                {"user_id": target_user_id},
            ).scalar_one()
        ) == 0

        standalone = conn.execute(
            text("SELECT id, email FROM app_users WHERE id = :user_id"),
            {"user_id": standalone_id},
        ).mappings().one()
        assert str(standalone["email"]).lower() == standalone_email, standalone
        assert_no_membership(conn, standalone_id)
        assert int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM auth_platform_user_roles
                    WHERE user_id = :user_id AND role_key = 'platform.platform_admin' AND active IS TRUE
                    """
                ),
                {"user_id": standalone_id},
            ).scalar_one()
        ) == 1

        audit = conn.execute(
            text(
                """
                SELECT actor_user_id, action, object_type, reason
                FROM auth_audit_log
                WHERE object_id = :user_id AND action = 'platform.role.granted'
                ORDER BY created_at DESC LIMIT 1
                """
            ),
            {"user_id": standalone_id},
        ).mappings().one()
        assert str(audit["actor_user_id"]) == ip_owner_id, audit
        assert str(audit["object_type"]) == "platform_user_role", audit
        assert str(audit["reason"]) == "platform.special_roles.manage", audit
        assert int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM auth_audit_log
                    WHERE actor_user_id = :user_id
                      AND action IN ('platform.role.granted', 'platform.role.revoked')
                    """
                ),
                {"user_id": superuser_id},
            ).scalar_one()
        ) == 0

        household = conn.execute(
            text("SELECT id, context_type FROM household_registry WHERE id = :household_id"),
            {"household_id": target_household_id},
        ).mappings().one()
        assert str(household["context_type"]) == "regular", household

    print(f"target_user_id={target_user_id}")
    print(f"target_household_id={target_household_id}")
    print(f"revoked_session_id={revoked_session_id}")
    print("P0_L4_07_PLATFORM_ROLE_WITHOUT_HOUSEHOLD_MEMBERSHIP_GREEN")
    print("P0_L4_07_TARGET_SESSION_REVOKED_GREEN")
    print("P0_L4_07_PLATFORM_SESSION_REMAINS_ACTIVE_GREEN")
    print("P0_L4_07_SUPERUSER_ROLE_BOUNDARY_GREEN")
    print("P0_L4_07_IP_OWNER_ROLE_GRANT_AUDIT_GREEN")
    print("P0_L4_07_STANDALONE_TARGET_NO_HOUSEHOLD_GREEN")
    print("P0_L4_07_POSTGRESQL_END_STATE_GREEN")
    return 0


def main() -> int:
    mode = str(sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode == "setup":
        return setup_platform_authority()
    if mode == "verify":
        return verify_end_state()
    raise SystemExit("Gebruik: l4_07_platform_browser_authority.py setup|verify")


if __name__ == "__main__":
    raise SystemExit(main())
