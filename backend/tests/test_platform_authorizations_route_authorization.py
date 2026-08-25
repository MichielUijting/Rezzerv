import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api.platform_authorizations_routes import (
    PLATFORM_AUTHORIZATIONS_PERMISSION,
    PLATFORM_SPECIAL_ROLE_MUTATION_PERMISSION,
)
from app.services.authorization_foundation_service import (
    ROLE_PERMISSIONS,
    ensure_authorization_foundation,
    evaluate_platform_permission,
)
from app.services.platform_authorization_management_service import (
    FRONTTEAM_ROLE_KEY,
    IP_OWNER_ROLE_KEY,
    MANAGED_SPECIAL_ROLE_KEYS,
    PLATFORM_ADMIN_ROLE_KEY,
    PLATFORM_SPECIAL_ROLES_MANAGE,
    SUPERUSER_ROLE_KEY,
    PlatformAuthorizationConflictError,
    grant_special_role,
    list_platform_authorizations,
    revoke_special_role,
)


def _engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _create_schema(conn):
    conn.execute(text("""
        CREATE TABLE app_users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            password_hash TEXT,
            account_status TEXT NOT NULL DEFAULT 'active'
        )
    """))
    conn.execute(text("""
        CREATE TABLE household_registry (
            id TEXT PRIMARY KEY,
            naam TEXT NOT NULL,
            context_type TEXT NOT NULL
        )
    """))
    conn.execute(text("INSERT INTO household_registry(id, naam, context_type) VALUES ('0', 'Systeem', 'system')"))
    conn.execute(text("""
        CREATE TABLE household_memberships (
            user_id TEXT NOT NULL,
            household_id TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            PRIMARY KEY(user_id, household_id)
        )
    """))
    ensure_authorization_foundation(conn)


def _insert_user(conn, user_id: str, email: str, *, status: str = "active"):
    conn.execute(text("""
        INSERT INTO app_users(id, email, password, password_hash, account_status)
        VALUES (:id, :email, 'secret-password', 'secret-hash', :status)
    """), {"id": user_id, "email": email, "status": status})


def _assign_role(conn, user_id: str, role_key: str):
    conn.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES (:user_id, :role_key, 1)
    """), {"user_id": user_id, "role_key": role_key})


def test_inventory_and_mutation_use_separate_canonical_permissions():
    assert PLATFORM_AUTHORIZATIONS_PERMISSION == "platform.permissions.manage"
    assert PLATFORM_SPECIAL_ROLE_MUTATION_PERMISSION == PLATFORM_SPECIAL_ROLES_MANAGE
    assert PLATFORM_SPECIAL_ROLE_MUTATION_PERMISSION == "platform.special_roles.manage"

    assert PLATFORM_AUTHORIZATIONS_PERMISSION in ROLE_PERMISSIONS["platform.platform_admin"]
    assert PLATFORM_AUTHORIZATIONS_PERMISSION in ROLE_PERMISSIONS["platform.ip_owner"]
    assert PLATFORM_SPECIAL_ROLE_MUTATION_PERMISSION in ROLE_PERMISSIONS["platform.ip_owner"]
    assert PLATFORM_SPECIAL_ROLE_MUTATION_PERMISSION not in ROLE_PERMISSIONS["platform.platform_admin"]
    assert PLATFORM_SPECIAL_ROLE_MUTATION_PERMISSION not in ROLE_PERMISSIONS["platform.superuser"]
    assert PLATFORM_SPECIAL_ROLE_MUTATION_PERMISSION not in ROLE_PERMISSIONS["platform.frontteam"]
    assert PLATFORM_SPECIAL_ROLE_MUTATION_PERMISSION not in ROLE_PERMISSIONS["household.admin"]


def test_inventory_is_safe_and_ip_owner_gets_all_three_managed_role_actions():
    engine = _engine()
    with engine.begin() as conn:
        _create_schema(conn)
        _insert_user(conn, "owner", "owner@example.test")
        _insert_user(conn, "target", "target@example.test")
        _insert_user(conn, "platform-admin", "platform-admin@example.test")
        _assign_role(conn, "owner", IP_OWNER_ROLE_KEY)
        _assign_role(conn, "platform-admin", PLATFORM_ADMIN_ROLE_KEY)

        owner_payload = list_platform_authorizations(conn, current_user_id="owner")
        admin_payload = list_platform_authorizations(conn, current_user_id="platform-admin")

        assert owner_payload["managed_role_keys"] == list(MANAGED_SPECIAL_ROLE_KEYS)
        assert owner_payload["can_manage_special_roles"] is True
        assert admin_payload["can_manage_special_roles"] is False
        managed_roles = {
            role["role_key"]
            for role in owner_payload["roles"]
            if role["managed_by_this_page"]
        }
        assert managed_roles == {SUPERUSER_ROLE_KEY, FRONTTEAM_ROLE_KEY, PLATFORM_ADMIN_ROLE_KEY}
        ip_owner_role = next(role for role in owner_payload["roles"] if role["role_key"] == IP_OWNER_ROLE_KEY)
        assert ip_owner_role["protected"] is True
        assert ip_owner_role["managed_by_this_page"] is False

        owner_target = next(item for item in owner_payload["users"] if item["user_id"] == "target")
        admin_target = next(item for item in admin_payload["users"] if item["user_id"] == "target")
        assert all(owner_target["role_actions"][role_key]["can_grant"] for role_key in MANAGED_SPECIAL_ROLE_KEYS)
        assert all(
            not admin_target["role_actions"][role_key]["can_grant"]
            for role_key in MANAGED_SPECIAL_ROLE_KEYS
        )
        rendered = repr(owner_payload).lower()
        assert "secret-password" not in rendered
        assert "secret-hash" not in rendered
        assert "password_hash" not in rendered
        assert "token" not in rendered


def test_ip_owner_can_stack_superuser_and_platform_admin_after_context_cutover():
    engine = _engine()
    with engine.begin() as conn:
        _create_schema(conn)
        _insert_user(conn, "owner", "owner@example.test")
        _insert_user(conn, "target", "target@example.test")
        _assign_role(conn, "owner", IP_OWNER_ROLE_KEY)

        grant_special_role(conn, "target", role_key=SUPERUSER_ROLE_KEY, actor_user_id="owner")
        owner_payload = list_platform_authorizations(conn, current_user_id="owner")
        target = next(item for item in owner_payload["users"] if item["user_id"] == "target")
        assert target["role_actions"][PLATFORM_ADMIN_ROLE_KEY]["can_grant"] is True
        assert target["role_actions"][PLATFORM_ADMIN_ROLE_KEY]["grant_blocked_reason"] is None

        stacked = grant_special_role(
            conn,
            "target",
            role_key=PLATFORM_ADMIN_ROLE_KEY,
            actor_user_id="owner",
        )
        assert set(stacked["platform_role_keys"]) == {
            SUPERUSER_ROLE_KEY,
            PLATFORM_ADMIN_ROLE_KEY,
        }
        assert evaluate_platform_permission(
            conn, user_id="target", permission_key=PLATFORM_AUTHORIZATIONS_PERMISSION
        ).allowed is True
        assert evaluate_platform_permission(
            conn, user_id="target", permission_key=PLATFORM_SPECIAL_ROLE_MUTATION_PERMISSION
        ).allowed is False

        with pytest.raises(PlatformAuthorizationConflictError, match="Frontteamlid"):
            grant_special_role(conn, "target", role_key=FRONTTEAM_ROLE_KEY, actor_user_id="owner")

        superuser_only = revoke_special_role(
            conn,
            "target",
            role_key=PLATFORM_ADMIN_ROLE_KEY,
            actor_user_id="owner",
        )
        assert superuser_only["platform_role_keys"] == [SUPERUSER_ROLE_KEY]

        platform_admin_only = grant_special_role(
            conn,
            "target",
            role_key=PLATFORM_ADMIN_ROLE_KEY,
            actor_user_id="owner",
        )
        revoke_special_role(
            conn,
            "target",
            role_key=SUPERUSER_ROLE_KEY,
            actor_user_id="owner",
        )
        assert platform_admin_only["platform_role_keys"] == [PLATFORM_ADMIN_ROLE_KEY, SUPERUSER_ROLE_KEY]
        owner_payload = list_platform_authorizations(conn, current_user_id="owner")
        target = next(item for item in owner_payload["users"] if item["user_id"] == "target")
        assert target["platform_role_keys"] == [PLATFORM_ADMIN_ROLE_KEY]
        assert target["role_actions"][SUPERUSER_ROLE_KEY]["can_grant"] is True


def test_ip_owner_target_is_immutable_and_suspended_grant_is_blocked():
    engine = _engine()
    with engine.begin() as conn:
        _create_schema(conn)
        _insert_user(conn, "owner", "owner@example.test")
        _insert_user(conn, "suspended", "suspended@example.test", status="suspended")
        _assign_role(conn, "owner", IP_OWNER_ROLE_KEY)

        with pytest.raises(PlatformAuthorizationConflictError, match="IP-eigenaar"):
            grant_special_role(conn, "owner", role_key=PLATFORM_ADMIN_ROLE_KEY, actor_user_id="owner")
        with pytest.raises(PlatformAuthorizationConflictError, match="geschorst"):
            grant_special_role(conn, "suspended", role_key=PLATFORM_ADMIN_ROLE_KEY, actor_user_id="owner")


def test_special_role_changes_are_audited_with_special_role_authority_reason():
    engine = _engine()
    with engine.begin() as conn:
        _create_schema(conn)
        _insert_user(conn, "owner", "owner@example.test")
        _insert_user(conn, "target", "target@example.test")
        _assign_role(conn, "owner", IP_OWNER_ROLE_KEY)

        grant_special_role(conn, "target", role_key=SUPERUSER_ROLE_KEY, actor_user_id="owner")
        audit = conn.execute(text("""
            SELECT actor_user_id, action, object_type, object_id, new_value, reason
            FROM auth_audit_log
            ORDER BY created_at DESC LIMIT 1
        """)).mappings().one()
        assert audit["actor_user_id"] == "owner"
        assert audit["action"] == "platform.role.granted"
        assert audit["object_type"] == "platform_user_role"
        assert audit["object_id"] == "target"
        assert SUPERUSER_ROLE_KEY in str(audit["new_value"])
        assert audit["reason"] == PLATFORM_SPECIAL_ROLES_MANAGE
