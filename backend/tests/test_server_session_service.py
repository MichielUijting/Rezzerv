from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text

from app.services.authorization_foundation_service import (
    ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS,
    ROLE_PERMISSIONS,
    V2_SUPERUSER_TARGET_PERMISSIONS,
    ensure_authorization_foundation,
)
from app.services.server_session_service import (
    create_none_server_session,
    create_server_session,
    create_system_server_session,
    ensure_server_session_schema,
    public_session_payload,
    resolve_session_context_type,
    resolve_server_session,
    revoke_server_session,
    rotate_active_household,
)
from app.testing.server_session_contract import create_server_session_contract_schema


@pytest.fixture()
def connection():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id VARCHAR(64) PRIMARY KEY,
                context_type TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO household_registry(id, context_type)
            VALUES ('0', 'system'), ('1', 'regular'), ('2', 'regular')
        """))
        conn.execute(text("CREATE TABLE app_users (id VARCHAR(64) PRIMARY KEY, email VARCHAR(255) NOT NULL)"))
        conn.execute(
            text(
                """
                CREATE TABLE household_memberships (
                    user_id VARCHAR(64) NOT NULL,
                    household_id VARCHAR(64) NOT NULL,
                    role VARCHAR(32) NOT NULL,
                    PRIMARY KEY (user_id, household_id)
                )
                """
            )
        )
        conn.execute(text("INSERT INTO app_users (id, email) VALUES ('u1', 'admin@rezzerv.local'), ('u2', 'lid@rezzerv.local')"))
        conn.execute(
            text(
                """
                INSERT INTO household_memberships (user_id, household_id, role)
                VALUES ('u1', '1', 'owner'), ('u1', '2', 'member'), ('u2', '2', 'member')
                """
            )
        )
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES
              ('1', 'u1', 'household.admin'),
              ('2', 'u1', 'household.member'),
              ('2', 'u2', 'household.member')
        """))
        create_server_session_contract_schema(conn)
        yield conn


def assert_http_status(exc: pytest.ExceptionInfo[HTTPException], status_code: int):
    assert exc.value.status_code == status_code


def test_missing_session_fails_closed(connection):
    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, None)
    assert_http_status(exc, 401)


def test_platform_admin_none_session_is_sql_null_and_resolves_without_membership(connection):
    connection.execute(text(
        "INSERT INTO app_users(id, email) VALUES ('platform-admin', 'platform@example.test')"
    ))
    connection.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES ('platform-admin', 'platform.platform_admin', 1)
    """))

    raw_session_id, created = create_none_server_session(
        connection,
        user_id='platform-admin',
    )
    resolved = resolve_server_session(connection, raw_session_id)
    stored_household_id = connection.execute(text("""
        SELECT active_household_id FROM server_sessions
        WHERE user_id = 'platform-admin'
    """)).scalar_one()

    assert stored_household_id is None
    assert created.active_household_id is resolved.active_household_id is None
    assert created.context_type == resolved.context_type == 'none'
    assert created.role is resolved.role is None
    expected_permissions = set(ROLE_PERMISSIONS['platform.platform_admin'])
    assert public_session_payload(resolved) == {
        'user': {'id': 'platform-admin', 'email': 'platform@example.test'},
        'user_id': 'platform-admin',
        'email': 'platform@example.test',
        'active_household_id': None,
        'active_household_name': '',
        'context_type': 'none',
        'role': None,
        'display_role': None,
        'permissions': {key: True for key in sorted(expected_permissions)},
        'supported_permissions': sorted(expected_permissions),
        'can_manage_member_permissions': False,
        'can_manage_members': False,
        'is_viewer': False,
        'is_platform_superuser': False,
        'is_frontteam': False,
        'session_version': 1,
        'expires_at': resolved.expires_at.isoformat(),
    }
    assert 'platform_roles' not in public_session_payload(resolved)


def test_none_session_fails_closed_when_platform_admin_role_is_deactivated(connection):
    connection.execute(text(
        "INSERT INTO app_users(id, email) VALUES ('platform-admin', 'platform@example.test')"
    ))
    connection.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES ('platform-admin', 'platform.platform_admin', 1)
    """))
    raw_session_id, _ = create_none_server_session(connection, user_id='platform-admin')
    connection.execute(text("""
        UPDATE auth_platform_user_roles SET active = 0
        WHERE user_id = 'platform-admin' AND role_key = 'platform.platform_admin'
    """))

    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_session_id)

    assert_http_status(exc, 403)


def test_none_session_creation_rejects_platform_admin_superuser_conflict(connection):
    connection.execute(text(
        "INSERT INTO app_users(id, email) VALUES ('platform-admin', 'platform@example.test')"
    ))
    connection.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES
          ('platform-admin', 'platform.platform_admin', 1),
          ('platform-admin', 'platform.superuser', 1)
    """))

    with pytest.raises(HTTPException) as exc:
        create_none_server_session(connection, user_id='platform-admin')

    assert_http_status(exc, 403)
    assert connection.execute(text(
        "SELECT COUNT(*) FROM server_sessions WHERE user_id = 'platform-admin'"
    )).scalar_one() == 0


def test_session_belongs_to_exactly_one_user_and_household(connection):
    raw_id, context = create_server_session(
        connection,
        user_id="u1",
        active_household_id="1",
    )

    resolved = resolve_server_session(connection, raw_id)

    assert resolved.user_id == "u1"
    assert resolved.active_household_id == "1"
    assert resolved.role == "admin"
    assert resolved.context_type == "regular"
    assert resolved.is_platform_superuser is False
    assert public_session_payload(resolved)["context_type"] == "regular"
    assert context.session_id == resolved.session_id


def test_household_zero_is_never_a_fallback(connection):
    with pytest.raises(HTTPException) as exc:
        create_server_session(connection, user_id="u1", active_household_id="0")
    assert_http_status(exc, 403)


def test_non_member_cannot_select_household(connection):
    with pytest.raises(HTTPException) as exc:
        create_server_session(connection, user_id="u2", active_household_id="1")
    assert_http_status(exc, 403)


def test_stale_legacy_role_does_not_change_canonical_session_role(connection):
    raw_id, _ = create_server_session(connection, user_id="u1", active_household_id="1")
    connection.execute(
        text("UPDATE household_memberships SET role = 'member' WHERE user_id = 'u1' AND household_id = '1'")
    )

    resolved = resolve_server_session(connection, raw_id)

    assert resolved.role == "admin"


def test_canonical_role_update_changes_session_role(connection):
    raw_id, _ = create_server_session(connection, user_id="u1", active_household_id="1")
    connection.execute(text("""
        UPDATE auth_membership_roles SET role_key = 'household.member'
        WHERE household_id = '1' AND membership_id = 'u1'
    """))

    resolved = resolve_server_session(connection, raw_id)

    assert resolved.role == "member"


def test_missing_role_never_escalates_to_superuser(connection):
    raw_id, _ = create_server_session(connection, user_id="u1", active_household_id="1")
    connection.execute(
        text("UPDATE auth_membership_roles SET active = 0 WHERE household_id = '1' AND membership_id = 'u1'")
    )

    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_id)
    assert_http_status(exc, 403)


def test_superuser_system_session_uses_platform_role_without_household_membership(connection):
    connection.execute(text("""
        INSERT INTO app_users (id, email)
        VALUES ('system-superuser', 'supergebruiker@rezzerv.local')
    """))
    connection.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES ('system-superuser', 'platform.superuser', 1)
    """))

    raw_id, created = create_system_server_session(
        connection,
        user_id='system-superuser',
    )
    resolved = resolve_server_session(connection, raw_id)
    payload = public_session_payload(resolved)

    assert created.role == resolved.role == 'owner'
    assert created.context_type == resolved.context_type == 'system'
    assert created.active_household_id == resolved.active_household_id == '0'
    assert created.is_platform_superuser is resolved.is_platform_superuser is True
    assert connection.execute(text("""
        SELECT COUNT(*) FROM household_memberships
        WHERE user_id = 'system-superuser'
    """)).scalar_one() == 0
    assert payload['context_type'] == 'system'
    assert payload['is_platform_superuser'] is True
    assert 'platform_roles' not in payload
    granted = {key for key, allowed in payload['permissions'].items() if allowed}
    assert ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS <= granted
    assert not (V2_SUPERUSER_TARGET_PERMISSIONS - ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS) & granted


def test_ip_owner_system_session_uses_platform_role_without_household_membership(connection):
    connection.execute(text("""
        INSERT INTO app_users (id, email)
        VALUES ('ip-owner', 'ip-owner@example.test')
    """))
    connection.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES ('ip-owner', 'platform.ip_owner', 1)
    """))

    raw_id, created = create_system_server_session(connection, user_id='ip-owner')
    resolved = resolve_server_session(connection, raw_id)
    payload = public_session_payload(resolved)

    assert created.context_type == resolved.context_type == 'system'
    assert created.active_household_id == resolved.active_household_id == '0'
    assert created.role == resolved.role == 'owner'
    assert created.is_platform_superuser is resolved.is_platform_superuser is False
    assert payload['is_platform_superuser'] is False
    assert 'platform_roles' not in payload


def test_fixed_superuser_email_without_active_role_cannot_create_household_zero_session(connection):
    connection.execute(text("""
        INSERT INTO app_users (id, email)
        VALUES ('email-only-superuser', 'supergebruiker@rezzerv.local')
    """))
    connection.execute(text("""
        INSERT INTO household_memberships (user_id, household_id, role)
        VALUES ('email-only-superuser', '0', 'owner')
    """))
    connection.execute(text("""
        INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
        VALUES ('0', 'email-only-superuser', 'household.admin')
    """))

    with pytest.raises(HTTPException) as exc:
        create_server_session(
            connection,
            user_id='email-only-superuser',
            active_household_id='0',
        )

    assert_http_status(exc, 403)
    assert connection.execute(text("""
        SELECT COUNT(*) FROM server_sessions
        WHERE user_id = 'email-only-superuser'
    """)).scalar_one() == 0


def test_system_session_fails_closed_after_platform_role_deactivation(connection):
    connection.execute(text("""
        INSERT INTO app_users (id, email)
        VALUES ('ip-owner', 'ip-owner@example.test')
    """))
    connection.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES ('ip-owner', 'platform.ip_owner', 1)
    """))
    raw_id, _ = create_system_server_session(connection, user_id='ip-owner')
    connection.execute(text("""
        UPDATE auth_platform_user_roles SET active = 0
        WHERE user_id = 'ip-owner' AND role_key = 'platform.ip_owner'
    """))

    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_id)

    assert_http_status(exc, 403)


def test_revoked_session_returns_401(connection):
    raw_id, _ = create_server_session(connection, user_id="u1", active_household_id="1")
    revoke_server_session(connection, raw_id)

    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_id)
    assert_http_status(exc, 401)


def test_expired_session_returns_401(connection):
    issued_at = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
    raw_id, _ = create_server_session(
        connection,
        user_id="u1",
        active_household_id="1",
        ttl=timedelta(minutes=5),
        now=issued_at,
    )

    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_id, now=issued_at + timedelta(minutes=6))
    assert_http_status(exc, 401)


def test_household_switch_rotates_and_invalidates_old_session(connection):
    raw_old, _ = create_server_session(connection, user_id="u1", active_household_id="1")

    raw_new, new_context = rotate_active_household(connection, raw_old, "2")

    assert raw_new != raw_old
    assert new_context.active_household_id == "2"
    assert resolve_server_session(connection, raw_new).active_household_id == "2"
    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_old)
    assert_http_status(exc, 401)


def test_new_login_invalidates_existing_user_session(connection):
    raw_old, _ = create_server_session(connection, user_id="u1", active_household_id="1")
    raw_new, _ = create_server_session(connection, user_id="u1", active_household_id="1")

    assert resolve_server_session(connection, raw_new).user_id == "u1"
    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, raw_old)
    assert_http_status(exc, 401)


def test_context_type_foundation_is_registry_authoritative(connection):
    assert resolve_session_context_type(connection, None) == "none"
    assert resolve_session_context_type(connection, "1") == "regular"
    assert resolve_session_context_type(connection, "0") == "system"


@pytest.mark.parametrize("household_id", ["missing", "", "demo-household"])
def test_context_type_foundation_never_falls_back(connection, household_id):
    with pytest.raises(HTTPException) as exc:
        resolve_session_context_type(connection, household_id)
    assert_http_status(exc, 403)


def test_context_type_foundation_rejects_unknown_registry_value(connection):
    connection.execute(text("""
        INSERT INTO household_registry(id, context_type)
        VALUES ('invalid', 'private')
    """))
    with pytest.raises(HTTPException) as exc:
        resolve_session_context_type(connection, "invalid")
    assert_http_status(exc, 403)


def test_explicit_test_schema_is_nullable_and_inert_shim_is_idempotent(connection):
    first_sql = connection.execute(text("""
        SELECT sql FROM sqlite_master
        WHERE type = 'table' AND name = 'server_sessions'
    """)).scalar_one()
    ensure_server_session_schema(connection)
    ensure_server_session_schema(connection)
    second_sql = connection.execute(text("""
        SELECT sql FROM sqlite_master
        WHERE type = 'table' AND name = 'server_sessions'
    """)).scalar_one()
    household_column = next(
        row for row in connection.exec_driver_sql("PRAGMA table_info(server_sessions)").mappings()
        if row["name"] == "active_household_id"
    )

    assert household_column["notnull"] == 0
    assert first_sql == second_sql


def test_inert_schema_shim_does_not_create_missing_table():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        assert inspect(conn).has_table("server_sessions") is False
        ensure_server_session_schema(conn)
        assert inspect(conn).has_table("server_sessions") is False


def test_inert_schema_shim_does_not_mutate_legacy_table():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE server_sessions (
                id VARCHAR(64) PRIMARY KEY,
                session_token_hash VARCHAR(64) NOT NULL UNIQUE,
                user_id VARCHAR(64) NOT NULL,
                active_household_id VARCHAR(64) NOT NULL,
                issued_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                session_version INTEGER NOT NULL DEFAULT 1,
                revoked_at TIMESTAMP NULL,
                replaced_by_session_id VARCHAR(64) NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        before_sql = conn.execute(text("""
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'server_sessions'
        """)).scalar_one()

        ensure_server_session_schema(conn)

        after_sql = conn.execute(text("""
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'server_sessions'
        """)).scalar_one()
        household_column = next(
            row for row in conn.exec_driver_sql("PRAGMA table_info(server_sessions)").mappings()
            if row["name"] == "active_household_id"
        )

    assert before_sql == after_sql
    assert household_column["notnull"] == 1
