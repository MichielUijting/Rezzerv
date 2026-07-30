import pytest
from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.authorization_membership_service import (
    AuthorizationDeniedError,
    migrate_legacy_household_memberships,
    require_household_permission,
    set_household_membership_role,
    set_household_permission_override,
)


def _connection():
    conn = create_engine("sqlite:///:memory:").connect()
    ensure_authorization_foundation(conn)
    return conn


def _assign(conn, household_id, membership_id, role_key):
    conn.execute(text("""
        INSERT INTO auth_membership_roles(household_id, membership_id, role_key, active)
        VALUES (:household_id, :membership_id, :role_key, 1)
    """), {
        "household_id": household_id,
        "membership_id": membership_id,
        "role_key": role_key,
    })


def test_legacy_memberships_migrate_admin_member_and_viewer():
    conn = _connection()
    conn.execute(text("""
        CREATE TABLE household_memberships (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            user_id TEXT,
            role TEXT,
            status TEXT
        )
    """))
    conn.execute(text("""
        INSERT INTO household_memberships(id, household_id, user_id, role, status)
        VALUES
          ('m-admin', 'h1', 'u1', 'beheerder', 'active'),
          ('m-member', 'h1', 'u2', 'member', 'active'),
          ('m-viewer', 'h1', 'u3', 'viewer', 'active')
    """))

    result = migrate_legacy_household_memberships(conn)
    roles = dict(conn.execute(text("""
        SELECT membership_id, role_key FROM auth_membership_roles
        ORDER BY membership_id
    """)).all())

    assert result.scanned == 3
    assert result.created == 3
    assert roles == {
        "m-admin": "household.admin",
        "m-member": "household.member",
        "m-viewer": "household.viewer",
    }


def test_migration_is_idempotent_and_preserves_explicit_role():
    conn = _connection()
    conn.execute(text("""
        CREATE TABLE household_memberships (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            role TEXT
        )
    """))
    conn.execute(text("""
        INSERT INTO household_memberships(id, household_id, role)
        VALUES ('m1', 'h1', 'beheerder')
    """))
    _assign(conn, 'h1', 'm1', 'household.viewer')

    result = migrate_legacy_household_memberships(conn)

    assert result.created == 0
    assert result.preserved == 1
    assert conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = 'h1' AND membership_id = 'm1'
    """)).scalar() == 'household.viewer'


def test_guard_allows_admin_and_denies_member_for_member_management():
    conn = _connection()
    _assign(conn, 'h1', 'admin', 'household.admin')
    _assign(conn, 'h1', 'member', 'household.member')

    assert require_household_permission(
        conn,
        household_id='h1',
        membership_id='admin',
        permission_key='members.manage',
    ).allowed

    with pytest.raises(AuthorizationDeniedError) as exc_info:
        require_household_permission(
            conn,
            household_id='h1',
            membership_id='member',
            permission_key='members.manage',
        )
    assert exc_info.value.decision.reason == 'not_granted'


def test_role_change_requires_permission_and_writes_audit():
    conn = _connection()
    _assign(conn, 'h1', 'admin', 'household.admin')
    _assign(conn, 'h1', 'target', 'household.member')

    set_household_membership_role(
        conn,
        household_id='h1',
        actor_membership_id='admin',
        actor_user_id='u-admin',
        target_membership_id='target',
        role_key='household.advanced_member',
        reason='Meer beheermogelijkheden nodig',
    )

    assert conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = 'h1' AND membership_id = 'target'
    """)).scalar() == 'household.advanced_member'
    assert conn.execute(text("""
        SELECT action FROM auth_audit_log WHERE object_id = 'target'
    """)).scalar() == 'authorization.membership_role.updated'


def test_last_admin_cannot_be_demoted():
    conn = _connection()
    _assign(conn, 'h1', 'admin', 'household.admin')

    with pytest.raises(ValueError, match='minimaal één actieve beheerder'):
        set_household_membership_role(
            conn,
            household_id='h1',
            actor_membership_id='admin',
            actor_user_id='u-admin',
            target_membership_id='admin',
            role_key='household.member',
        )


def test_permission_override_requires_permission_and_deny_wins():
    conn = _connection()
    _assign(conn, 'h1', 'admin', 'household.admin')
    _assign(conn, 'h1', 'target', 'household.admin')

    set_household_permission_override(
        conn,
        household_id='h1',
        actor_membership_id='admin',
        actor_user_id='u-admin',
        target_membership_id='target',
        permission_key='inventory.view',
        effect='deny',
        reason='Tijdelijke beperking',
    )

    with pytest.raises(AuthorizationDeniedError) as exc_info:
        require_household_permission(
            conn,
            household_id='h1',
            membership_id='target',
            permission_key='inventory.view',
        )
    assert exc_info.value.decision.reason == 'explicit_deny'


def test_household_scope_cannot_assign_platform_permission():
    conn = _connection()
    _assign(conn, 'h1', 'admin', 'household.admin')

    with pytest.raises(ValueError, match='Platform permissions'):
        set_household_permission_override(
            conn,
            household_id='h1',
            actor_membership_id='admin',
            actor_user_id='u-admin',
            target_membership_id='admin',
            permission_key='platform.permissions.manage',
            effect='allow',
        )
