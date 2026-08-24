import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api.platform_authorizations_routes import PLATFORM_AUTHORIZATIONS_PERMISSION
from app.services.authorization_foundation_service import (
    PLATFORM_PERMISSIONS,
    ROLE_PERMISSIONS,
    ensure_authorization_foundation,
    evaluate_platform_permission,
)
from app.services.platform_authorization_management_service import (
    PLATFORM_ADMIN_ROLE_KEY,
    PlatformAuthorizationConflictError,
    grant_platform_admin,
    list_platform_authorizations,
    revoke_platform_admin,
)


def _engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _create_users(conn):
    conn.execute(text("""
        CREATE TABLE app_users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            password_hash TEXT,
            account_status TEXT NOT NULL DEFAULT 'active'
        )
    """))


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


def test_platform_authorizations_uses_existing_canonical_permission_matrix():
    assert PLATFORM_AUTHORIZATIONS_PERMISSION == "platform.permissions.manage"
    assert PLATFORM_AUTHORIZATIONS_PERMISSION in ROLE_PERMISSIONS["platform.platform_admin"]
    assert PLATFORM_AUTHORIZATIONS_PERMISSION in ROLE_PERMISSIONS["platform.ip_owner"]
    assert PLATFORM_AUTHORIZATIONS_PERMISSION in ROLE_PERMISSIONS["platform.superuser"]
    assert PLATFORM_AUTHORIZATIONS_PERMISSION not in ROLE_PERMISSIONS["platform.frontteam"]
    assert PLATFORM_AUTHORIZATIONS_PERMISSION not in ROLE_PERMISSIONS["platform.support_read"]
    assert PLATFORM_AUTHORIZATIONS_PERMISSION not in ROLE_PERMISSIONS["household.admin"]
    assert set(ROLE_PERMISSIONS["platform.superuser"]) == set(PLATFORM_PERMISSIONS)


def test_authorization_inventory_is_safe_and_only_platform_admin_is_mutable():
    engine = _engine()
    with engine.begin() as conn:
        _create_users(conn)
        ensure_authorization_foundation(conn)
        _insert_user(conn, "actor", "actor@example.test")
        _insert_user(conn, "admin", "admin@example.test")
        _insert_user(conn, "owner", "owner@example.test")
        _insert_user(conn, "support", "support@example.test")
        _assign_role(conn, "actor", "platform.ip_owner")
        _assign_role(conn, "admin", PLATFORM_ADMIN_ROLE_KEY)
        _assign_role(conn, "owner", "platform.superuser")
        _assign_role(conn, "support", "platform.support_read")

        payload = list_platform_authorizations(conn, current_user_id="actor")

        assert payload["managed_role_key"] == PLATFORM_ADMIN_ROLE_KEY
        managed_roles = [role["role_key"] for role in payload["roles"] if role["managed_by_this_page"]]
        assert managed_roles == [PLATFORM_ADMIN_ROLE_KEY]
        protected = {
            role["role_key"]
            for role in payload["roles"]
            if not role["managed_by_this_page"]
        }
        assert "platform.ip_owner" in protected
        assert "platform.superuser" in protected
        assert "platform.frontteam" in protected
        assert "platform.support_read" in protected

        by_id = {item["user_id"]: item for item in payload["users"]}
        assert by_id["actor"]["is_current"] is True
        assert by_id["admin"]["has_platform_admin"] is True
        assert by_id["admin"]["can_revoke_platform_admin"] is True
        assert by_id["support"]["can_grant_platform_admin"] is True
        rendered = repr(payload).lower()
        assert "secret-password" not in rendered
        assert "secret-hash" not in rendered
        assert "password_hash" not in rendered
        assert "token" not in rendered


def test_grant_platform_admin_is_live_and_audited_without_touching_other_roles():
    engine = _engine()
    with engine.begin() as conn:
        _create_users(conn)
        ensure_authorization_foundation(conn)
        _insert_user(conn, "actor", "actor@example.test")
        _insert_user(conn, "target", "target@example.test")
        _assign_role(conn, "actor", "platform.ip_owner")
        _assign_role(conn, "target", "platform.frontteam")

        before = evaluate_platform_permission(
            conn, user_id="target", permission_key=PLATFORM_AUTHORIZATIONS_PERMISSION
        )
        assert before.allowed is False

        item = grant_platform_admin(conn, "target", actor_user_id="actor")
        assert item["has_platform_admin"] is True
        assert set(item["platform_role_keys"]) == {"platform.frontteam", PLATFORM_ADMIN_ROLE_KEY}
        after = evaluate_platform_permission(
            conn, user_id="target", permission_key=PLATFORM_AUTHORIZATIONS_PERMISSION
        )
        assert after.allowed is True

        audit = conn.execute(text("""
            SELECT actor_user_id, action, object_type, object_id, new_value
            FROM auth_audit_log
            ORDER BY created_at DESC LIMIT 1
        """)).mappings().one()
        assert audit["actor_user_id"] == "actor"
        assert audit["action"] == "platform.role.granted"
        assert audit["object_type"] == "platform_user_role"
        assert audit["object_id"] == "target"
        assert PLATFORM_ADMIN_ROLE_KEY in str(audit["new_value"])


def test_revoke_platform_admin_is_live_audited_and_preserves_special_role():
    engine = _engine()
    with engine.begin() as conn:
        _create_users(conn)
        ensure_authorization_foundation(conn)
        _insert_user(conn, "actor", "actor@example.test")
        _insert_user(conn, "target", "target@example.test")
        _assign_role(conn, "actor", "platform.superuser")
        _assign_role(conn, "target", "platform.ip_owner")
        _assign_role(conn, "target", PLATFORM_ADMIN_ROLE_KEY)

        item = revoke_platform_admin(conn, "target", actor_user_id="actor")
        assert item["has_platform_admin"] is False
        assert item["platform_role_keys"] == ["platform.ip_owner"]
        assert evaluate_platform_permission(
            conn, user_id="target", permission_key=PLATFORM_AUTHORIZATIONS_PERMISSION
        ).allowed is True
        assert conn.execute(text("""
            SELECT active FROM auth_platform_user_roles
            WHERE user_id = 'target' AND role_key = 'platform.ip_owner'
        """)).scalar_one() == 1
        audit = conn.execute(text("""
            SELECT action, old_value, new_value FROM auth_audit_log
            ORDER BY created_at DESC LIMIT 1
        """)).mappings().one()
        assert audit["action"] == "platform.role.revoked"
        assert PLATFORM_ADMIN_ROLE_KEY in str(audit["old_value"])
        assert audit["new_value"] is None


def test_self_revoke_is_blocked():
    engine = _engine()
    with engine.begin() as conn:
        _create_users(conn)
        ensure_authorization_foundation(conn)
        _insert_user(conn, "actor", "actor@example.test")
        _assign_role(conn, "actor", PLATFORM_ADMIN_ROLE_KEY)
        with pytest.raises(PlatformAuthorizationConflictError, match="eigen Platformbeheerder-rol"):
            revoke_platform_admin(conn, "actor", actor_user_id="actor")


def test_revoke_cannot_remove_last_active_manage_authority():
    engine = _engine()
    with engine.begin() as conn:
        _create_users(conn)
        ensure_authorization_foundation(conn)
        _insert_user(conn, "actor", "actor@example.test")
        _insert_user(conn, "target", "target@example.test")
        _assign_role(conn, "target", PLATFORM_ADMIN_ROLE_KEY)

    with pytest.raises(PlatformAuthorizationConflictError, match="Minimaal één actief account"):
        with engine.begin() as conn:
            revoke_platform_admin(conn, "target", actor_user_id="actor")

    with engine.connect() as conn:
        assert conn.execute(text("""
            SELECT active FROM auth_platform_user_roles
            WHERE user_id = 'target' AND role_key = :role_key
        """), {"role_key": PLATFORM_ADMIN_ROLE_KEY}).scalar_one() == 1


def test_suspended_account_cannot_receive_platform_admin():
    engine = _engine()
    with engine.begin() as conn:
        _create_users(conn)
        ensure_authorization_foundation(conn)
        _insert_user(conn, "actor", "actor@example.test")
        _insert_user(conn, "target", "target@example.test", status="suspended")
        _assign_role(conn, "actor", "platform.ip_owner")
        with pytest.raises(PlatformAuthorizationConflictError, match="geschorst account"):
            grant_platform_admin(conn, "target", actor_user_id="actor")
