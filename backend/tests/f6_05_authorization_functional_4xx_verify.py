from __future__ import annotations

import os
import sys

from sqlalchemy import text

from app.db import engine
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.testing.postgresql_onboarding_selftest_fixture import seed_household, seed_user


IP_OWNER_ROLE_KEY = "platform.ip_owner"
SYSTEM_HOUSEHOLD_ID = "0"


def required(name: str) -> str:
    value = str(os.environ.get(name, "")).strip()
    if not value:
        raise AssertionError(f"{name} ontbreekt voor F6-05")
    return value


def prove_runtime_boundary() -> None:
    assert engine.dialect.name == "postgresql", engine.dialect.name
    with engine.begin() as conn:
        current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
        runtime_create = bool(
            conn.execute(
                text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            ).scalar_one()
        )
    assert current_user == "rezzerv_app", current_user
    assert runtime_create is False
    print("F6_05_POSTGRESQL_RUNTIME_BOUNDARY_GREEN")


def setup_ip_owner() -> int:
    prove_runtime_boundary()
    user_id = required("F6_05_IP_OWNER_USER_ID")
    email = required("F6_05_IP_OWNER_EMAIL").lower()
    password = required("F6_05_IP_OWNER_PASSWORD")

    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        if int(
            conn.execute(
                text("SELECT COUNT(*) FROM household_registry WHERE id = :household_id"),
                {"household_id": SYSTEM_HOUSEHOLD_ID},
            ).scalar_one()
        ) == 0:
            seed_household(
                conn,
                household_id=SYSTEM_HOUSEHOLD_ID,
                name="Systeem",
                context_type="system",
            )

        duplicate = int(
            conn.execute(
                text("SELECT COUNT(*) FROM app_users WHERE lower(trim(email)) = :email"),
                {"email": email},
            ).scalar_one()
        )
        assert duplicate == 0, (email, duplicate)
        seed_user(conn, user_id=user_id, email=email, password=password)
        conn.execute(
            text(
                """
                INSERT INTO auth_platform_user_roles (user_id, role_key, active)
                VALUES (:user_id, :role_key, TRUE)
                """
            ),
            {"user_id": user_id, "role_key": IP_OWNER_ROLE_KEY},
        )
        active_role = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM auth_platform_user_roles
                    WHERE user_id = :user_id
                      AND role_key = :role_key
                      AND active IS TRUE
                    """
                ),
                {"user_id": user_id, "role_key": IP_OWNER_ROLE_KEY},
            ).scalar_one()
        )
        assert active_role == 1, active_role

    print("F6_05_IP_OWNER_FIXTURE_GREEN")
    return 0


def verify_rejected_mutations() -> int:
    prove_runtime_boundary()
    account_email = required("F6_05_ACCOUNT_EMAIL").lower()
    ip_owner_user_id = required("F6_05_IP_OWNER_USER_ID")
    missing_target_id = required("F6_05_MISSING_TARGET_USER_ID")

    with engine.begin() as conn:
        account_rows = conn.execute(
            text(
                """
                SELECT id, email
                FROM app_users
                WHERE lower(trim(email)) = :email
                """
            ),
            {"email": account_email},
        ).mappings().all()
        assert len(account_rows) == 1, account_rows
        account_user_id = str(account_rows[0]["id"])

        membership_count = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM household_memberships
                    WHERE lower(trim(user_email)) = :email
                    """
                ),
                {"email": account_email},
            ).scalar_one()
        )
        assert membership_count == 1, membership_count

        session_count = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM server_sessions
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": account_user_id},
            ).scalar_one()
        )
        assert session_count == 1, session_count

        missing_user_count = int(
            conn.execute(
                text("SELECT COUNT(*) FROM app_users WHERE id = :user_id"),
                {"user_id": missing_target_id},
            ).scalar_one()
        )
        assert missing_user_count == 0, missing_user_count

        missing_role_count = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM auth_platform_user_roles
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": missing_target_id},
            ).scalar_one()
        )
        assert missing_role_count == 0, missing_role_count

        missing_audit_count = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM auth_audit_log
                    WHERE object_id = :user_id
                      AND action IN ('platform.role.granted', 'platform.role.revoked')
                    """
                ),
                {"user_id": missing_target_id},
            ).scalar_one()
        )
        assert missing_audit_count == 0, missing_audit_count

        ip_owner_role_count = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM auth_platform_user_roles
                    WHERE user_id = :user_id
                      AND role_key = :role_key
                      AND active IS TRUE
                    """
                ),
                {"user_id": ip_owner_user_id, "role_key": IP_OWNER_ROLE_KEY},
            ).scalar_one()
        )
        assert ip_owner_role_count == 1, ip_owner_role_count

    print(f"account_user_id={account_user_id}")
    print("F6_05_ACCOUNT_DUPLICATE_REGISTRATION_NO_POLLUTION_GREEN")
    print("F6_05_PLATFORM_MISSING_TARGET_NO_POLLUTION_GREEN")
    print("F6_05_POSTGRESQL_REJECTED_MUTATIONS_GREEN")
    return 0


def main() -> int:
    mode = str(sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode == "setup":
        return setup_ip_owner()
    if mode == "verify":
        return verify_rejected_mutations()
    raise SystemExit(
        "Gebruik: f6_05_authorization_functional_4xx_verify.py setup|verify"
    )


if __name__ == "__main__":
    raise SystemExit(main())
