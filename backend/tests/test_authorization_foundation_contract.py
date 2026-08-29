from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import (
    ADMIN_PERMISSIONS,
    HOUSEHOLD_PERMISSIONS,
    PLATFORM_PERMISSIONS,
    ROLE_PERMISSIONS,
    V2_PLATFORM_PERMISSIONS,
    assert_last_household_admin_remains,
    ensure_authorization_foundation,
    evaluate_household_permission,
    evaluate_platform_permission,
    write_authorization_audit,
)


_AUTHORIZATION_SCHEMA = (
    """
    CREATE TABLE auth_permissions (
        permission_key TEXT PRIMARY KEY,
        scope TEXT NOT NULL CHECK (scope IN ('household', 'platform')),
        description TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE auth_roles (
        role_key TEXT PRIMARY KEY,
        scope TEXT NOT NULL CHECK (scope IN ('household', 'platform')),
        name TEXT NOT NULL,
        system_role INTEGER NOT NULL DEFAULT 1,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE auth_role_permissions (
        role_key TEXT NOT NULL,
        permission_key TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (role_key, permission_key)
    )
    """,
    """
    CREATE TABLE auth_membership_roles (
        household_id TEXT NOT NULL,
        membership_id TEXT NOT NULL,
        role_key TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (household_id, membership_id)
    )
    """,
    """
    CREATE TABLE auth_membership_permission_overrides (
        household_id TEXT NOT NULL,
        membership_id TEXT NOT NULL,
        permission_key TEXT NOT NULL,
        effect TEXT NOT NULL CHECK (effect IN ('allow', 'deny')),
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (household_id, membership_id, permission_key)
    )
    """,
    """
    CREATE TABLE auth_platform_user_roles (
        user_id TEXT NOT NULL,
        role_key TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, role_key)
    )
    """,
    """
    CREATE TABLE auth_support_sessions (
        id TEXT PRIMARY KEY,
        support_user_id TEXT NOT NULL,
        household_id TEXT NOT NULL,
        access_level TEXT NOT NULL CHECK (access_level IN ('metadata', 'read', 'mutate', 'emergency')),
        reason TEXT NOT NULL,
        ticket_reference TEXT NOT NULL,
        starts_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE auth_audit_log (
        id TEXT PRIMARY KEY,
        actor_user_id TEXT NOT NULL,
        actor_type TEXT NOT NULL,
        household_id TEXT,
        support_session_id TEXT,
        action TEXT NOT NULL,
        object_type TEXT,
        object_id TEXT,
        old_value TEXT,
        new_value TEXT,
        reason TEXT,
        ticket_reference TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX idx_auth_single_active_ip_owner
    ON auth_platform_user_roles(role_key)
    WHERE role_key = 'platform.ip_owner' AND active = 1
    """,
)


def _install_migration_owned_authorization_schema(conn) -> None:
    for statement in _AUTHORIZATION_SCHEMA:
        conn.execute(text(statement))


def make_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        _install_migration_owned_authorization_schema(conn)
    return engine


def test_unmigrated_authorization_schema_fails_closed_without_runtime_ddl():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        before = tuple(conn.execute(text(
            "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
        )).all())
        with pytest.raises(RuntimeError, match="niet gemigreerd"):
            ensure_authorization_foundation(conn)
        after = tuple(conn.execute(text(
            "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
        )).all())
    assert after == before


def test_registry_and_system_roles_are_seeded_idempotently():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        ensure_authorization_foundation(conn)
        permission_count = conn.execute(text("SELECT COUNT(*) FROM auth_permissions")).scalar_one()
        role_count = conn.execute(text("SELECT COUNT(*) FROM auth_roles")).scalar_one()
    assert permission_count == (
        len(HOUSEHOLD_PERMISSIONS)
        + len(PLATFORM_PERMISSIONS)
        + len(V2_PLATFORM_PERMISSIONS)
    )
    assert role_count == len(ROLE_PERMISSIONS)


def test_household_admin_receives_matrix_admin_rights_but_no_platform_rights():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('household-a', 'member-admin', 'household.admin')
        """))
        for permission_key in HOUSEHOLD_PERMISSIONS:
            decision = evaluate_household_permission(
                conn,
                household_id="household-a",
                membership_id="member-admin",
                permission_key=permission_key,
            )
            assert decision.allowed is (permission_key in ADMIN_PERMISSIONS), permission_key
        wrong_scope = evaluate_household_permission(
            conn,
            household_id="household-a",
            membership_id="member-admin",
            permission_key="platform.audit.view",
        )
    assert not wrong_scope.allowed
    assert wrong_scope.reason == "unknown_or_wrong_scope"


def test_explicit_deny_wins_over_role_grant_and_allow_can_extend_role():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('household-a', 'member-1', 'household.member')
        """))
        conn.execute(text("""
            INSERT INTO auth_membership_permission_overrides(
                household_id, membership_id, permission_key, effect, reason
            ) VALUES
                ('household-a', 'member-1', 'inventory.update', 'deny', 'read only stock'),
                ('household-a', 'member-1', 'receipts.delete', 'allow', 'trusted member')
        """))
        denied = evaluate_household_permission(
            conn,
            household_id="household-a",
            membership_id="member-1",
            permission_key="inventory.update",
        )
        extended = evaluate_household_permission(
            conn,
            household_id="household-a",
            membership_id="member-1",
            permission_key="receipts.delete",
        )
    assert denied.allowed is False
    assert denied.reason == "explicit_deny"
    assert extended.allowed is True
    assert extended.reason == "explicit_allow"


def test_household_context_is_strictly_isolated():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('household-a', 'member-1', 'household.admin')
        """))
        same_household = evaluate_household_permission(
            conn,
            household_id="household-a",
            membership_id="member-1",
            permission_key="inventory.update",
        )
        other_household = evaluate_household_permission(
            conn,
            household_id="household-b",
            membership_id="member-1",
            permission_key="inventory.update",
        )
    assert same_household.allowed is True
    assert other_household.allowed is False


def test_unknown_permission_is_denied_by_default():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        decision = evaluate_household_permission(
            conn,
            household_id="household-a",
            membership_id="member-1",
            permission_key="inventory.destroy_everything",
        )
    assert decision.allowed is False
    assert decision.reason == "unknown_or_wrong_scope"


def test_platform_role_is_separate_from_household_membership():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key)
            VALUES ('support-1', 'platform.support_read')
        """))
        metadata = evaluate_platform_permission(
            conn,
            user_id="support-1",
            permission_key="platform.households.view_metadata",
        )
        mutate = evaluate_platform_permission(
            conn,
            user_id="support-1",
            permission_key="platform.support_access.mutate",
        )
        household = evaluate_household_permission(
            conn,
            household_id="household-a",
            membership_id="support-1",
            permission_key="inventory.view",
        )
    assert metadata.allowed is True
    assert mutate.allowed is False
    assert household.allowed is False


def test_last_active_household_admin_cannot_be_removed():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('household-a', 'admin-1', 'household.admin')
        """))
        with pytest.raises(ValueError, match="minimaal één actieve beheerder"):
            assert_last_household_admin_remains(
                conn,
                household_id="household-a",
                membership_id_to_remove="admin-1",
            )
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('household-a', 'admin-2', 'household.admin')
        """))
        assert_last_household_admin_remains(
            conn,
            household_id="household-a",
            membership_id_to_remove="admin-1",
        )


def test_authorization_audit_is_append_only_by_service_contract():
    engine = make_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        first_id = write_authorization_audit(
            conn,
            actor_user_id="admin-1",
            actor_type="household_user",
            household_id="household-a",
            action="permission.override.created",
            object_type="membership",
            object_id="member-1",
            old_value=None,
            new_value={"permission_key": "inventory.update", "effect": "deny"},
            reason="tijdelijk alleen lezen",
        )
        second_id = write_authorization_audit(
            conn,
            actor_user_id="admin-1",
            actor_type="household_user",
            household_id="household-a",
            action="permission.override.removed",
            object_type="membership",
            object_id="member-1",
            old_value={"permission_key": "inventory.update", "effect": "deny"},
            new_value=None,
            reason="toegang hersteld",
        )
        rows = conn.execute(text("SELECT id, action FROM auth_audit_log ORDER BY created_at, id")).mappings().all()
    assert first_id != second_id
    assert len(rows) == 2
    assert {row["action"] for row in rows} == {
        "permission.override.created",
        "permission.override.removed",
    }
