from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.frontteam_household_provisioning import resolve_frontteam_personal_household_id
from app.services.platform_authorization_management_service import (
    FRONTTEAM_ROLE_KEY,
    IP_OWNER_ROLE_KEY,
    PLATFORM_ADMIN_ROLE_KEY,
    PLATFORM_SPECIAL_ROLES_MANAGE,
    SUPERUSER_ROLE_KEY,
    PlatformAuthorizationConflictError,
    grant_special_role,
    list_platform_authorizations,
    revoke_special_role,
)


@pytest.fixture()
def connection():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                context_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            INSERT INTO household_registry(id, naam, context_type)
            VALUES ('0', 'Systeem', 'system'), ('1', 'Regulier', 'regular')
        """))
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                account_status TEXT NOT NULL DEFAULT 'active'
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                user_id TEXT NOT NULL,
                household_id TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id, household_id)
            )
        """))
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO app_users(id, email, account_status)
            VALUES
              ('owner', 'owner@example.test', 'active'),
              ('target', 'target@example.test', 'active'),
              ('front', 'front@example.test', 'active'),
              ('regular', 'regular@example.test', 'active'),
              ('suspended', 'suspended@example.test', 'suspended'),
              ('platform-admin', 'platform-admin@example.test', 'active')
        """))
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES
              ('owner', 'platform.ip_owner', 1),
              ('platform-admin', 'platform.platform_admin', 1)
        """))
        conn.execute(text("""
            INSERT INTO household_memberships(user_id, household_id, role, status)
            VALUES ('regular', '1', 'admin', 'active')
        """))
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key, active)
            VALUES ('1', 'regular', 'household.admin', 1)
        """))
        yield conn


def active_roles(conn, user_id: str) -> set[str]:
    return set(conn.execute(text("""
        SELECT role_key FROM auth_platform_user_roles
        WHERE user_id = :user_id AND active = 1
    """), {"user_id": user_id}).scalars().all())


def test_inventory_exposes_special_role_actions_only_to_ip_owner(connection):
    owner_inventory = list_platform_authorizations(connection, current_user_id="owner")
    admin_inventory = list_platform_authorizations(connection, current_user_id="platform-admin")

    assert owner_inventory["special_roles_permission"] == PLATFORM_SPECIAL_ROLES_MANAGE
    assert owner_inventory["can_manage_special_roles"] is True
    assert admin_inventory["can_manage_special_roles"] is False

    owner_target = next(item for item in owner_inventory["users"] if item["user_id"] == "target")
    admin_target = next(item for item in admin_inventory["users"] if item["user_id"] == "target")
    assert owner_target["role_actions"][SUPERUSER_ROLE_KEY]["can_grant"] is True
    assert owner_target["role_actions"][PLATFORM_ADMIN_ROLE_KEY]["can_grant"] is True
    assert owner_target["role_actions"][FRONTTEAM_ROLE_KEY]["can_grant"] is True
    assert all(
        action["can_grant"] is False and action["can_revoke"] is False
        for action in admin_target["role_actions"].values()
    )


def test_ip_owner_is_protected_from_ordinary_special_role_management(connection):
    inventory = list_platform_authorizations(connection, current_user_id="owner")
    owner = next(item for item in inventory["users"] if item["user_id"] == "owner")
    assert owner["is_ip_owner"] is True
    assert all(
        action["can_grant"] is False and action["can_revoke"] is False
        for action in owner["role_actions"].values()
    )

    with pytest.raises(PlatformAuthorizationConflictError, match="IP-eigenaar"):
        grant_special_role(
            connection,
            "owner",
            role_key=PLATFORM_ADMIN_ROLE_KEY,
            actor_user_id="owner",
        )


def test_superuser_and_platform_admin_can_be_stacked_in_canonical_storage(connection):
    grant_special_role(
        connection,
        "target",
        role_key=SUPERUSER_ROLE_KEY,
        actor_user_id="owner",
    )
    grant_special_role(
        connection,
        "target",
        role_key=PLATFORM_ADMIN_ROLE_KEY,
        actor_user_id="owner",
    )

    assert active_roles(connection, "target") == {
        SUPERUSER_ROLE_KEY,
        PLATFORM_ADMIN_ROLE_KEY,
    }

    revoke_special_role(
        connection,
        "target",
        role_key=PLATFORM_ADMIN_ROLE_KEY,
        actor_user_id="owner",
    )
    assert active_roles(connection, "target") == {SUPERUSER_ROLE_KEY}


def test_frontteam_grant_provisions_personal_household_and_revoke_retains_it(connection):
    grant_special_role(
        connection,
        "front",
        role_key=FRONTTEAM_ROLE_KEY,
        actor_user_id="owner",
    )
    household_id = resolve_frontteam_personal_household_id(connection, "front")
    assert household_id
    assert active_roles(connection, "front") == {FRONTTEAM_ROLE_KEY}
    membership = connection.execute(text("""
        SELECT hm.role, hm.status, mr.role_key, mr.active
        FROM household_memberships hm
        JOIN auth_membership_roles mr
          ON mr.household_id = hm.household_id
         AND mr.membership_id = hm.user_id
        WHERE hm.user_id = 'front' AND hm.household_id = :household_id
    """), {"household_id": household_id}).mappings().one()
    assert membership["role"] == "admin"
    assert membership["status"] == "active"
    assert membership["role_key"] == "household.admin"
    assert membership["active"] == 1

    revoke_special_role(
        connection,
        "front",
        role_key=FRONTTEAM_ROLE_KEY,
        actor_user_id="owner",
    )
    assert active_roles(connection, "front") == set()
    assert resolve_frontteam_personal_household_id(connection, "front") == household_id
    assert connection.execute(text("""
        SELECT COUNT(*) FROM household_memberships
        WHERE user_id = 'front' AND household_id = :household_id
    """), {"household_id": household_id}).scalar_one() == 1

    grant_special_role(
        connection,
        "front",
        role_key=FRONTTEAM_ROLE_KEY,
        actor_user_id="owner",
    )
    assert resolve_frontteam_personal_household_id(connection, "front") == household_id


def test_frontteam_cannot_stack_with_system_or_platform_admin_roles(connection):
    grant_special_role(
        connection,
        "target",
        role_key=PLATFORM_ADMIN_ROLE_KEY,
        actor_user_id="owner",
    )
    with pytest.raises(PlatformAuthorizationConflictError, match="Frontteamlid"):
        grant_special_role(
            connection,
            "target",
            role_key=FRONTTEAM_ROLE_KEY,
            actor_user_id="owner",
        )

    grant_special_role(
        connection,
        "front",
        role_key=FRONTTEAM_ROLE_KEY,
        actor_user_id="owner",
    )
    with pytest.raises(PlatformAuthorizationConflictError, match="Frontteamlid"):
        grant_special_role(
            connection,
            "front",
            role_key=SUPERUSER_ROLE_KEY,
            actor_user_id="owner",
        )


def test_first_frontteam_grant_rejects_unrelated_regular_membership(connection):
    with pytest.raises(PlatformAuthorizationConflictError, match="persoonlijk huishouden"):
        grant_special_role(
            connection,
            "regular",
            role_key=FRONTTEAM_ROLE_KEY,
            actor_user_id="owner",
        )


def test_system_roles_reject_regular_household_membership(connection):
    for role_key in (SUPERUSER_ROLE_KEY, PLATFORM_ADMIN_ROLE_KEY):
        with pytest.raises(PlatformAuthorizationConflictError, match="geen regulier huishoudlidmaatschap"):
            grant_special_role(
                connection,
                "regular",
                role_key=role_key,
                actor_user_id="owner",
            )


def test_suspended_account_cannot_receive_special_role_but_existing_role_can_be_revoked(connection):
    with pytest.raises(PlatformAuthorizationConflictError, match="geschorst"):
        grant_special_role(
            connection,
            "suspended",
            role_key=PLATFORM_ADMIN_ROLE_KEY,
            actor_user_id="owner",
        )

    connection.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES ('suspended', 'platform.platform_admin', 1)
    """))
    revoke_special_role(
        connection,
        "suspended",
        role_key=PLATFORM_ADMIN_ROLE_KEY,
        actor_user_id="owner",
    )
    assert active_roles(connection, "suspended") == set()


def test_role_change_audit_uses_exact_special_role_permission(connection):
    grant_special_role(
        connection,
        "target",
        role_key=SUPERUSER_ROLE_KEY,
        actor_user_id="owner",
    )
    row = connection.execute(text("""
        SELECT action, object_id, reason
        FROM auth_audit_log
        WHERE object_type = 'platform_user_role'
        ORDER BY id DESC
        LIMIT 1
    """)).mappings().one()
    assert row["action"] == "platform.role.granted"
    assert row["object_id"] == "target"
    assert row["reason"] == PLATFORM_SPECIAL_ROLES_MANAGE
