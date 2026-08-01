from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.server_session_service import (
    create_server_session,
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
    assert resolved.role == "owner"
    assert context.session_id == resolved.session_id


def test_household_zero_is_never_a_fallback(connection):
    with pytest.raises(HTTPException) as exc:
        create_server_session(connection, user_id="u1", active_household_id="0")
    assert_http_status(exc, 403)


def test_non_member_cannot_select_household(connection):
    with pytest.raises(HTTPException) as exc:
        create_server_session(connection, user_id="u2", active_household_id="1")
    assert_http_status(exc, 403)


def test_role_is_resolved_from_database_for_every_request(connection):
    raw_id, _ = create_server_session(connection, user_id="u1", active_household_id="1")
    connection.execute(
        text("UPDATE household_memberships SET role = 'member' WHERE user_id = 'u1' AND household_id = '1'")
    )

    resolved = resolve_server_session(connection, raw_id)

    assert resolved.role == "member"


def test_missing_role_never_escalates_to_superuser(connection):
    raw_id, _ = create_server_session(connection, user_id="u1", active_household_id="1")
    connection.execute(
        text("UPDATE household_memberships SET role = '' WHERE user_id = 'u1' AND household_id = '1'")
    )

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
