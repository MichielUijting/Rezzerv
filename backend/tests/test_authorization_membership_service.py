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


def test_legacy_memberships_migrate_to_dutch_roles():
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
          ('m-owner', 'h1', 'u1', 'beheerder', 'active'),
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
        "m-owner": "huishouden.eigenaar",
        "m-member": "huishouden.lid",
        "m-viewer": "huishouden.kijker",
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
    _assign(conn, 'h1', 'm1', 'huishouden.kijker')

    result = migrate_legacy_household_memberships(conn)

    assert result.created == 0
    assert result.preserved == 1
    assert conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = 'h1' AND membership_id = 'm1'
    """)).scalar() == 'huishouden.kijker'


def test_owner_can_manage_members_and_member_cannot():
    conn = _connection()
    _assign(conn, 'h1', 'owner', 'huishouden.eigenaar')
    _assign(conn, 'h1', 'member', 'huishouden.lid')

    assert require_household_permission(
        conn,
        household_id='h1',
        membership_id='owner',
        permission_key='members.manage',
    ).allowed

    with pytest.raises(AuthorizationDeniedError):
        require_household_permission(
            conn,
            household_id='h1',
            membership_id='member',
            permission_key='members.manage',
        )


def test_owner_can_change_member_to_viewer_and_audit_is_written():
    conn = _connection()
    _assign(conn, 'h1', 'owner', 'huishouden.eigenaar')
    _assign(conn, 'h1', 'target', 'huishouden.lid')

    set_household_membership_role(
        conn,
        household_id='h1',
        actor_membership_id='owner',
        actor_user_id='u-owner',
        target_membership_id='target',
        role_key='huishouden.kijker',
        reason='Alleen meekijken',
    )

    assert conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = 'h1' AND membership_id = 'target'
    """)).scalar() == 'huishouden.kijker'
    assert conn.execute(text("""
        SELECT action FROM auth_audit_log WHERE object_id = 'target'
    """)).scalar() == 'autorisatie.huishoudrol.gewijzigd'


def test_owner_cannot_demote_self_without_transfer():
    conn = _connection()
    _assign(conn, 'h1', 'owner', 'huishouden.eigenaar')

    with pytest.raises(ValueError, match='eigenaarschap'):
        set_household_membership_role(
            conn,
            household_id='h1',
            actor_membership_id='owner',
            actor_user_id='u-owner',
            target_membership_id='owner',
            role_key='huishouden.lid',
        )


def test_ownership_transfer_demotes_previous_owner():
    conn = _connection()
    _assign(conn, 'h1', 'owner', 'huishouden.eigenaar')
    _assign(conn, 'h1', 'target', 'huishouden.lid')

    set_household_membership_role(
        conn,
        household_id='h1',
        actor_membership_id='owner',
        actor_user_id='u-owner',
        target_membership_id='target',
        role_key='huishouden.eigenaar',
    )

    roles = dict(conn.execute(text("""
        SELECT membership_id, role_key FROM auth_membership_roles
        WHERE household_id = 'h1'
    """)).all())
    assert roles == {
        'owner': 'huishouden.lid',
        'target': 'huishouden.eigenaar',
    }


def test_individual_permission_overrides_are_disabled():
    conn = _connection()
    with pytest.raises(ValueError, match='niet beschikbaar'):
        set_household_permission_override(
            conn,
            household_id='h1',
            actor_membership_id='owner',
            actor_user_id='u-owner',
            target_membership_id='target',
            permission_key='inventory.view',
            effect='deny',
        )
