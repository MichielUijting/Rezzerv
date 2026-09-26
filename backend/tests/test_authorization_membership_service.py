import pytest
from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.authorization_membership_service import (
    AuthorizationDeniedError,
    CANONICAL_ROLE_COMPATIBILITY_MIRROR,
    create_canonical_membership_role,
    legacy_role_key,
    migrate_legacy_household_memberships,
    require_household_permission,
    resolve_effective_household_role,
    set_household_membership_role,
    set_household_permission_override,
)
from app.testing.authorization_schema_fixture import install_authorization_schema


def _connection():
    conn = create_engine("sqlite:///:memory:").connect()
    install_authorization_schema(conn)
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


def test_legacy_memberships_migrate_admin_member_viewer_and_advanced_member():
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
          ('m-advanced', 'h1', 'u4', 'advanced_member', 'active'),
          ('m-member', 'h1', 'u2', 'member', 'active'),
          ('m-viewer', 'h1', 'u3', 'viewer', 'active')
    """))

    result = migrate_legacy_household_memberships(conn)
    roles = dict(conn.execute(text("""
        SELECT membership_id, role_key FROM auth_membership_roles
        ORDER BY membership_id
    """)).all())

    assert result.scanned == 4
    assert result.created == 4
    assert roles == {
        "m-advanced": "household.advanced_member",
        "m-admin": "household.admin",
        "m-member": "household.member",
        "m-viewer": "household.viewer",
    }


def test_context_aware_backfill_preserves_legacy_semantics_and_fails_closed():
    conn = _connection()
    conn.execute(text("""
        CREATE TABLE household_registry (
            id TEXT PRIMARY KEY,
            context_type TEXT NOT NULL
        )
    """))
    conn.execute(text("""
        CREATE TABLE household_memberships (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            role TEXT,
            status TEXT
        )
    """))
    conn.execute(text("""
        INSERT INTO household_registry(id, context_type)
        VALUES ('h1', 'regular'), ('0', 'system')
    """))
    conn.execute(text("""
        INSERT INTO household_memberships(id, household_id, role, status)
        VALUES
          ('member', 'h1', 'member', 'active'),
          ('admin', 'h1', 'admin', 'active'),
          ('owner', 'h1', 'owner', 'active'),
          ('viewer', 'h1', 'viewer', 'active'),
          ('advanced', 'h1', 'advanced_member', 'active'),
          ('frontteam', 'h1', 'frontteam', 'active'),
          ('system-owner', '0', 'owner', 'active'),
          ('invalid', 'h1', 'unexpected-role', 'active')
    """))

    first = migrate_legacy_household_memberships(conn)
    second = migrate_legacy_household_memberships(conn)
    roles = dict(conn.execute(text("""
        SELECT membership_id, role_key FROM auth_membership_roles
        ORDER BY membership_id
    """)).all())

    assert roles == {
        'member': 'household.member',
        'admin': 'household.admin',
        'owner': 'household.admin',
        'viewer': 'household.viewer',
        'advanced': 'household.advanced_member',
        'frontteam': 'household.frontteam',
        'system-owner': 'household.owner',
    }
    assert first.created == 7
    assert first.invalid == 1
    assert second.created == 0
    assert second.preserved == 7
    assert second.invalid == 1


def test_existing_canonical_role_is_authoritative_and_never_rewritten():
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
        VALUES ('m1', 'h1', 'owner')
    """))
    _assign(conn, 'h1', 'm1', 'household.admin')

    result = migrate_legacy_household_memberships(conn)
    effective = resolve_effective_household_role(
        conn,
        household_id='h1',
        membership_id='m1',
        legacy_role='owner',
    )

    assert result.preserved == 1
    assert effective == 'household.admin'
    assert conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = 'h1' AND membership_id = 'm1'
    """)).scalar_one() == 'household.admin'
    assert conn.execute(text("SELECT role FROM household_memberships WHERE id = 'm1'" )).scalar_one() == 'owner'


def test_household_zero_keeps_temporary_owner_compatibility_without_rewrites():
    conn = _connection()
    conn.execute(text("""
        CREATE TABLE household_memberships (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            role TEXT
        )
    """))
    conn.execute(text("INSERT INTO household_memberships VALUES ('m0', '0', 'owner')"))
    _assign(conn, '0', 'm0', 'household.admin')

    effective = resolve_effective_household_role(
        conn,
        household_id='0',
        membership_id='m0',
        legacy_role='owner',
    )

    assert effective == 'household.owner'
    assert conn.execute(text("SELECT role FROM household_memberships WHERE id = 'm0'" )).scalar_one() == 'owner'
    assert conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = '0' AND membership_id = 'm0'
    """)).scalar_one() == 'household.admin'


def test_legacy_mapping_is_explicit_and_unknown_values_are_invalid():
    assert legacy_role_key('owner') == 'household.admin'
    assert legacy_role_key('frontteam') == 'household.frontteam'
    assert legacy_role_key('owner', system_household=True) == 'household.owner'
    assert legacy_role_key('unexpected-role') is None


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


def test_stale_legacy_roles_cannot_add_or_remove_canonical_permissions():
    conn = _connection()
    conn.execute(text("""
        CREATE TABLE household_memberships (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """))
    conn.execute(text("""
        INSERT INTO household_memberships VALUES
          ('canonical-member', 'h1', 'owner'),
          ('canonical-admin', 'h1', 'member')
    """))
    _assign(conn, 'h1', 'canonical-member', 'household.member')
    _assign(conn, 'h1', 'canonical-admin', 'household.admin')

    with pytest.raises(AuthorizationDeniedError):
        require_household_permission(
            conn,
            household_id='h1',
            membership_id='canonical-member',
            permission_key='members.manage',
        )
    assert require_household_permission(
        conn,
        household_id='h1',
        membership_id='canonical-admin',
        permission_key='members.manage',
    ).allowed
    with pytest.raises(AuthorizationDeniedError):
        require_household_permission(
            conn,
            household_id='h2',
            membership_id='canonical-admin',
            permission_key='members.manage',
        )


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
        role_key='household.admin',
        reason='Huishoudbeheer nodig',
    )

    assert conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = 'h1' AND membership_id = 'target'
    """)).scalar() == 'household.admin'
    assert conn.execute(text("""
        SELECT action FROM auth_audit_log WHERE object_id = 'target'
    """)).scalar() == 'authorization.membership_role.updated'


def test_supported_role_change_updates_canonical_and_compatibility_mirror():
    assert CANONICAL_ROLE_COMPATIBILITY_MIRROR['household.admin'] == 'admin'
    assert CANONICAL_ROLE_COMPATIBILITY_MIRROR['household.member'] == 'member'
    assert CANONICAL_ROLE_COMPATIBILITY_MIRROR['household.admin'] != 'owner'

    conn = _connection()
    conn.execute(text("""
        CREATE TABLE household_memberships (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """))
    conn.execute(text("""
        INSERT INTO household_memberships VALUES
          ('admin', 'h1', 'owner'),
          ('target', 'h1', 'member')
    """))
    _assign(conn, 'h1', 'admin', 'household.admin')
    _assign(conn, 'h1', 'target', 'household.member')

    set_household_membership_role(
        conn,
        household_id='h1',
        actor_membership_id='admin',
        actor_user_id='u-admin',
        target_membership_id='target',
        role_key='household.admin',
    )

    assert conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = 'h1' AND membership_id = 'target'
    """)).scalar_one() == 'household.admin'
    assert conn.execute(text("SELECT role FROM household_memberships WHERE id = 'target'" )).scalar_one() == 'admin'

    set_household_membership_role(
        conn,
        household_id='h1',
        actor_membership_id='admin',
        actor_user_id='u-admin',
        target_membership_id='target',
        role_key='household.member',
    )

    assert conn.execute(text("SELECT role FROM household_memberships WHERE id = 'target'" )).scalar_one() == 'member'
    assert conn.execute(text("""
        SELECT COUNT(*) FROM household_memberships
        WHERE household_id = 'h1' AND id = 'target' AND role = 'owner'
    """)).scalar_one() == 0


def test_new_membership_gets_canonical_role_without_overwriting_existing_role():
    conn = _connection()
    created = create_canonical_membership_role(
        conn,
        household_id='h1',
        membership_id='new-member',
        legacy_role='member',
    )
    assert created == 'household.member'
    _assign(conn, 'h1', 'existing', 'household.viewer')
    preserved_mapping = create_canonical_membership_role(
        conn,
        household_id='h1',
        membership_id='existing',
        legacy_role='owner',
    )
    assert preserved_mapping == 'household.admin'
    assert conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = 'h1' AND membership_id = 'existing'
    """)).scalar_one() == 'household.viewer'


@pytest.mark.parametrize('role_key', (
    'household.viewer',
    'household.advanced_member',
    'household.owner',
    'household.frontteam',
))
def test_household_management_cannot_assign_legacy_or_special_roles(role_key):
    conn = _connection()
    _assign(conn, 'h1', 'admin', 'household.admin')
    _assign(conn, 'h1', 'target', 'household.viewer')

    with pytest.raises(ValueError, match='Unknown or non-household role'):
        set_household_membership_role(
            conn,
            household_id='h1',
            actor_membership_id='admin',
            actor_user_id='u-admin',
            target_membership_id='target',
            role_key=role_key,
        )

    assert conn.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = 'h1' AND membership_id = 'target'
    """)).scalar() == 'household.viewer'


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


def test_stale_legacy_admin_cannot_defeat_canonical_last_admin_protection():
    conn = _connection()
    conn.execute(text("""
        CREATE TABLE household_memberships (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """))
    conn.execute(text("""
        INSERT INTO household_memberships VALUES
          ('admin', 'h1', 'member'),
          ('stale-owner', 'h1', 'owner')
    """))
    _assign(conn, 'h1', 'admin', 'household.admin')
    _assign(conn, 'h1', 'stale-owner', 'household.member')

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
