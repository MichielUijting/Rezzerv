from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import (
    ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS,
    V2_SUPERUSER_TARGET_PERMISSIONS,
    ensure_authorization_foundation,
)
from app.services.server_session_service import (
    create_server_session,
    public_session_payload,
    resolve_server_session,
    revoke_server_session,
    rotate_active_household,
)


@pytest.fixture()
def connection():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
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
        yield conn


def assert_http_status(exc: pytest.ExceptionInfo[HTTPException], status_code: int):
    assert exc.value.status_code == status_code


def test_missing_session_fails_closed(connection):
    with pytest.raises(HTTPException) as exc:
        resolve_server_session(connection, None)
    assert_http_status(exc, 401)


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


def test_household_zero_keeps_temporary_v1_1_owner_session_compatibility(connection):
    connection.execute(text("""
        INSERT INTO app_users (id, email)
        VALUES ('system-superuser', 'supergebruiker@rezzerv.local')
    """))
    connection.execute(text("""
        INSERT INTO household_memberships (user_id, household_id, role)
        VALUES ('system-superuser', '0', 'owner')
    """))
    connection.execute(text("""
        INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
        VALUES ('0', 'system-superuser', 'household.admin')
    """))

    raw_id, created = create_server_session(
        connection,
        user_id='system-superuser',
        active_household_id='0',
    )
    resolved = resolve_server_session(connection, raw_id)
    payload = public_session_payload(resolved)

    assert created.role == 'owner'
    assert resolved.role == 'owner'
    assert connection.execute(text("""
        SELECT role_key FROM auth_membership_roles
        WHERE household_id = '0' AND membership_id = 'system-superuser'
    """)).scalar_one() == 'household.admin'
    assert connection.execute(text("""
        SELECT role FROM household_memberships
        WHERE household_id = '0' AND user_id = 'system-superuser'
    """)).scalar_one() == 'owner'
    granted = {key for key, allowed in payload['permissions'].items() if allowed}
    assert ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS <= granted
    assert not (V2_SUPERUSER_TARGET_PERMISSIONS - ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS) & granted


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
