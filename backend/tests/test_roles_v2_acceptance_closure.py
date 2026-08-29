from __future__ import annotations

import ast
import inspect
import textwrap

from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import (
    ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS,
    FRONTTEAM_PLATFORM_PERMISSIONS,
    IP_OWNER_PERMISSIONS,
    PLATFORM_ADMIN_PERMISSIONS,
    ROLE_PERMISSIONS,
    V2_SUPERUSER_TARGET_PERMISSIONS,
    ensure_authorization_foundation,
)
from app.services.authorization_membership_service import (
    REGULAR_LEGACY_ROLE_KEYS,
    set_household_membership_role,
)
from app.services.server_session_service import (
    SYSTEM_PLATFORM_ROLES,
    create_system_server_session,
    public_session_payload,
    resolve_server_session,
)
from app.testing.server_session_contract import create_server_session_contract_schema
from app.testing.authorization_schema_fixture import install_authorization_schema


def _platform_permissions(role_key: str) -> set[str]:
    return {
        permission
        for permission in ROLE_PERMISSIONS[role_key]
        if permission.startswith("platform.")
    }


def test_v2_platform_role_permission_boundaries_are_exact():
    assert ROLE_PERMISSIONS["platform.superuser"] == set(V2_SUPERUSER_TARGET_PERMISSIONS)
    assert ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS == set(V2_SUPERUSER_TARGET_PERMISSIONS)
    assert ROLE_PERMISSIONS["platform.platform_admin"] == set(PLATFORM_ADMIN_PERMISSIONS)
    assert ROLE_PERMISSIONS["platform.frontteam"] == set(FRONTTEAM_PLATFORM_PERMISSIONS)
    assert ROLE_PERMISSIONS["platform.ip_owner"] == set(IP_OWNER_PERMISSIONS)

    assert not (V2_SUPERUSER_TARGET_PERMISSIONS & PLATFORM_ADMIN_PERMISSIONS)
    assert "platform.special_roles.manage" not in V2_SUPERUSER_TARGET_PERMISSIONS
    assert "platform.special_roles.manage" not in PLATFORM_ADMIN_PERMISSIONS
    assert IP_OWNER_PERMISSIONS == (
        V2_SUPERUSER_TARGET_PERMISSIONS
        | PLATFORM_ADMIN_PERMISSIONS
        | {"platform.special_roles.manage"}
    )


def test_superuser_platform_admin_stack_is_union_without_owner_only_authority():
    stacked = (
        ROLE_PERMISSIONS["platform.superuser"]
        | ROLE_PERMISSIONS["platform.platform_admin"]
    )
    assert stacked == V2_SUPERUSER_TARGET_PERMISSIONS | PLATFORM_ADMIN_PERMISSIONS
    assert "platform.special_roles.manage" not in stacked
    assert stacked < ROLE_PERMISSIONS["platform.ip_owner"]


def test_v2_context_role_partition_is_explicit():
    assert SYSTEM_PLATFORM_ROLES == frozenset({"platform.superuser", "platform.ip_owner"})
    assert "platform.platform_admin" not in SYSTEM_PLATFORM_ROLES
    assert "platform.frontteam" not in SYSTEM_PLATFORM_ROLES


def test_existing_function_domains_follow_v2_role_partition():
    frontteam = _platform_permissions("platform.frontteam")
    superuser = _platform_permissions("platform.superuser")
    platform_admin = _platform_permissions("platform.platform_admin")
    ip_owner = _platform_permissions("platform.ip_owner")

    # Meldingen/support is functioneel Superuser/IP-owner beheer.
    assert "platform.support_access.mutate" in superuser
    assert "platform.support_access.mutate" in ip_owner
    assert "platform.support_access.mutate" not in frontteam
    assert "platform.support_access.mutate" not in platform_admin

    # Externe productbronnen zijn functioneel voor Frontteam/Superuser/IP-owner.
    for permission in {
        "platform.external_products.view",
        "platform.external_products.search",
        "platform.external_products.link_existing",
    }:
        assert permission in frontteam
        assert permission in superuser
        assert permission in ip_owner
        assert permission not in platform_admin

    # Centrale catalogus, GPC en externe databronconfiguratie zijn functioneel.
    for permission in {
        "platform.catalog.manage",
        "platform.gpc.manage",
        "platform.external_sources.manage",
    }:
        assert permission in superuser
        assert permission in ip_owner
        assert permission not in frontteam
        assert permission not in platform_admin

    # Technische configuratie is Platformbeheerder/IP-owner, niet gewone Superuser.
    assert "platform.technical_configuration.manage" in platform_admin
    assert "platform.technical_configuration.manage" in ip_owner
    assert "platform.technical_configuration.manage" not in superuser
    assert "platform.technical_configuration.manage" not in frontteam


def test_legacy_household_roles_are_preserved_but_not_normally_assignable():
    # Compatibility/migration recognizes historical data non-destructively.
    assert REGULAR_LEGACY_ROLE_KEYS["viewer"] == "household.viewer"
    assert REGULAR_LEGACY_ROLE_KEYS["advanced_member"] == "household.advanced_member"
    assert "household.viewer" in ROLE_PERMISSIONS
    assert "household.advanced_member" in ROLE_PERMISSIONS

    # The normal household role mutation boundary exposes only member/admin.
    source = textwrap.dedent(inspect.getsource(set_household_membership_role))
    tree = ast.parse(source)
    allowed_roles = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "allowed_roles" for target in node.targets):
                if isinstance(node.value, ast.Set):
                    allowed_roles = {
                        element.value
                        for element in node.value.elts
                        if isinstance(element, ast.Constant)
                    }
                    break
    assert allowed_roles == {"household.member", "household.admin"}
    assert "household.viewer" not in allowed_roles
    assert "household.advanced_member" not in allowed_roles


def test_ip_owner_only_system_session_projects_exact_platform_union_without_role_list():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id VARCHAR(64) PRIMARY KEY,
                context_type TEXT NOT NULL
            )
        """))
        conn.execute(text("INSERT INTO household_registry(id, context_type) VALUES ('0', 'system')"))
        conn.execute(text("CREATE TABLE app_users (id VARCHAR(64) PRIMARY KEY, email VARCHAR(255) NOT NULL)"))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                user_id VARCHAR(64) NOT NULL,
                household_id VARCHAR(64) NOT NULL,
                role VARCHAR(32) NOT NULL,
                PRIMARY KEY (user_id, household_id)
            )
        """))
        conn.execute(text("INSERT INTO app_users(id, email) VALUES ('owner', 'owner@example.test')"))
        install_authorization_schema(conn)
        ensure_authorization_foundation(conn)
        create_server_session_contract_schema(conn)
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('owner', 'platform.ip_owner', 1)
        """))

        raw_session_id, created = create_system_server_session(conn, user_id="owner")
        resolved = resolve_server_session(conn, raw_session_id)
        payload = public_session_payload(resolved)

        assert created.context_type == resolved.context_type == "system"
        assert created.active_household_id == resolved.active_household_id == "0"
        assert created.is_ip_owner is True
        assert resolved.is_ip_owner is True
        assert created.is_platform_superuser is False
        assert created.is_platform_admin is False
        assert "platform_roles" not in payload

        projected_platform_permissions = {
            permission
            for permission, allowed in payload["permissions"].items()
            if allowed and permission.startswith("platform.")
        }
        assert projected_platform_permissions == set(ROLE_PERMISSIONS["platform.ip_owner"])
        assert "platform.special_roles.manage" in projected_platform_permissions
        assert V2_SUPERUSER_TARGET_PERMISSIONS <= projected_platform_permissions
        assert PLATFORM_ADMIN_PERMISSIONS <= projected_platform_permissions