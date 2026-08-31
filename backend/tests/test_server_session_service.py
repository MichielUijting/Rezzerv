from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect, text

from app.services.authorization_foundation_service import (
    ROLE_PERMISSIONS,
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
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
    seed_household,
    seed_membership,
    seed_user,
)


def assert_http_status(exc: pytest.ExceptionInfo[HTTPException], status_code: int):
    assert exc.value.status_code == status_code


def _seed_regular_fixture():
    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        seed_household(conn, household_id="0", name="Systeem", context_type="system")
        seed_household(conn, household_id="1", name="Huishouden 1", context_type="regular")
        seed_household(conn, household_id="2", name="Huishouden 2", context_type="regular")
        seed_user(conn, user_id="u1", email="admin@rezzerv.local", password="Rezzerv123")
        seed_user(conn, user_id="u2", email="lid@rezzerv.local", password="Rezzerv123")
        seed_membership(
            conn,
            membership_id="m-u1-h1",
            household_id="1",
            user_id="u1",
            email="admin@rezzerv.local",
            role="admin",
        )
        seed_membership(
            conn,
            membership_id="m-u1-h2",
            household_id="2",
            user_id="u1",
            email="admin@rezzerv.local",
            role="member",
        )
        seed_membership(
            conn,
            membership_id="m-u2-h2",
            household_id="2",
            user_id="u2",
            email="lid@rezzerv.local",
            role="member",
        )
    return engine


def test_missing_session_fails_closed():
    engine = _seed_regular_fixture()
    try:
        with engine.begin() as conn:
            with pytest.raises(HTTPException) as exc:
                resolve_server_session(conn, None)
            assert_http_status(exc, 401)
    finally:
        engine.dispose()


def test_regular_session_uses_canonical_role_and_ignores_stale_legacy_role():
    engine = _seed_regular_fixture()
    try:
        with engine.begin() as conn:
            raw_id, created = create_server_session(
                conn,
                user_id="u1",
                active_household_id="1",
            )
            assert created.role == "admin"
            conn.execute(text("""
                UPDATE household_memberships SET role = 'member'
                WHERE id = 'm-u1-h1'
            """))
            resolved = resolve_server_session(conn, raw_id)
            assert resolved.role == "admin"
            conn.execute(text("""
                UPDATE auth_membership_roles
                SET role_key = 'household.member'
                WHERE household_id = '1' AND membership_id = 'm-u1-h1'
            """))
            resolved = resolve_server_session(conn, raw_id)
            assert resolved.role == "member"
            assert resolved.context_type == "regular"
            assert public_session_payload(resolved)["active_household_id"] == "1"
    finally:
        engine.dispose()


def test_regular_user_cannot_select_system_or_nonmember_household():
    engine = _seed_regular_fixture()
    try:
        with engine.begin() as conn:
            with pytest.raises(HTTPException) as system_exc:
                create_server_session(conn, user_id="u1", active_household_id="0")
            assert_http_status(system_exc, 403)
            with pytest.raises(HTTPException) as outsider_exc:
                create_server_session(conn, user_id="u2", active_household_id="1")
            assert_http_status(outsider_exc, 403)
    finally:
        engine.dispose()


def test_platform_admin_none_session_is_sql_null_and_role_revocation_fails_closed():
    engine = _seed_regular_fixture()
    try:
        with engine.begin() as conn:
            seed_user(
                conn,
                user_id="platform-admin",
                email="platform@example.test",
                password="Rezzerv123",
            )
            conn.execute(text("""
                INSERT INTO auth_platform_user_roles(user_id, role_key, active)
                VALUES ('platform-admin', 'platform.platform_admin', TRUE)
            """))
            raw_id, created = create_none_server_session(conn, user_id="platform-admin")
            resolved = resolve_server_session(conn, raw_id)
            stored_household_id = conn.execute(text("""
                SELECT active_household_id FROM server_sessions
                WHERE user_id = 'platform-admin'
            """)).scalar_one()
            assert stored_household_id is None
            assert created.active_household_id is resolved.active_household_id is None
            assert created.context_type == resolved.context_type == "none"
            assert created.role is resolved.role is None
            expected_permissions = set(ROLE_PERMISSIONS["platform.platform_admin"])
            payload = public_session_payload(resolved)
            assert set(payload["permissions"]) == expected_permissions
            assert "platform_roles" not in payload

            conn.execute(text("""
                UPDATE auth_platform_user_roles SET active = FALSE
                WHERE user_id = 'platform-admin'
                  AND role_key = 'platform.platform_admin'
            """))
            with pytest.raises(HTTPException) as exc:
                resolve_server_session(conn, raw_id)
            assert_http_status(exc, 403)
    finally:
        engine.dispose()


def test_platform_admin_superuser_conflict_creates_no_none_session():
    engine = _seed_regular_fixture()
    try:
        with engine.begin() as conn:
            seed_user(
                conn,
                user_id="platform-admin",
                email="platform@example.test",
                password="Rezzerv123",
            )
            conn.execute(text("""
                INSERT INTO auth_platform_user_roles(user_id, role_key, active)
                VALUES
                  ('platform-admin', 'platform.platform_admin', TRUE),
                  ('platform-admin', 'platform.superuser', TRUE)
            """))
            with pytest.raises(HTTPException) as exc:
                create_none_server_session(conn, user_id="platform-admin")
            assert_http_status(exc, 403)
            assert conn.execute(text("""
                SELECT COUNT(*) FROM server_sessions
                WHERE user_id = 'platform-admin'
            """)).scalar_one() == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("user_id", "email", "role_key", "is_superuser"),
    [
        ("system-superuser", SUPERGEBRUIKER_EMAIL, "platform.superuser", True),
        ("ip-owner", "ip-owner@example.test", "platform.ip_owner", False),
    ],
)
def test_system_session_uses_active_platform_role_without_household_membership(
    user_id,
    email,
    role_key,
    is_superuser,
):
    engine = _seed_regular_fixture()
    try:
        with engine.begin() as conn:
            seed_user(conn, user_id=user_id, email=email, password="Rezzerv123")
            conn.execute(text("""
                INSERT INTO auth_platform_user_roles(user_id, role_key, active)
                VALUES (:user_id, :role_key, TRUE)
            """), {"user_id": user_id, "role_key": role_key})
            raw_id, created = create_system_server_session(conn, user_id=user_id)
            resolved = resolve_server_session(conn, raw_id)
            payload = public_session_payload(resolved)
            assert created.context_type == resolved.context_type == "system"
            assert created.active_household_id == resolved.active_household_id == "0"
            assert created.role == resolved.role == "owner"
            assert resolved.is_platform_superuser is is_superuser
            assert payload["is_platform_superuser"] is is_superuser
            assert "platform_roles" not in payload

            conn.execute(text("""
                UPDATE auth_platform_user_roles SET active = FALSE
                WHERE user_id = :user_id AND role_key = :role_key
            """), {"user_id": user_id, "role_key": role_key})
            with pytest.raises(HTTPException) as exc:
                resolve_server_session(conn, raw_id)
            assert_http_status(exc, 403)
    finally:
        engine.dispose()


def test_revoked_and_expired_sessions_fail_closed():
    engine = _seed_regular_fixture()
    try:
        with engine.begin() as conn:
            raw_id, _ = create_server_session(conn, user_id="u1", active_household_id="1")
            revoke_server_session(conn, raw_id)
            with pytest.raises(HTTPException) as revoked:
                resolve_server_session(conn, raw_id)
            assert_http_status(revoked, 401)

            issued_at = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
            expiring_id, _ = create_server_session(
                conn,
                user_id="u1",
                active_household_id="1",
                ttl=timedelta(minutes=5),
                now=issued_at,
            )
            with pytest.raises(HTTPException) as expired:
                resolve_server_session(
                    conn,
                    expiring_id,
                    now=issued_at + timedelta(minutes=6),
                )
            assert_http_status(expired, 401)
    finally:
        engine.dispose()


def test_household_switch_and_new_login_invalidate_previous_session():
    engine = _seed_regular_fixture()
    try:
        with engine.begin() as conn:
            raw_old, _ = create_server_session(conn, user_id="u1", active_household_id="1")
            raw_switched, switched = rotate_active_household(conn, raw_old, "2")
            assert switched.active_household_id == "2"
            assert resolve_server_session(conn, raw_switched).active_household_id == "2"
            with pytest.raises(HTTPException):
                resolve_server_session(conn, raw_old)

            raw_latest, _ = create_server_session(conn, user_id="u1", active_household_id="1")
            assert resolve_server_session(conn, raw_latest).user_id == "u1"
            with pytest.raises(HTTPException):
                resolve_server_session(conn, raw_switched)
    finally:
        engine.dispose()


def test_context_type_is_registry_authoritative_and_never_falls_back():
    engine = _seed_regular_fixture()
    try:
        with engine.begin() as conn:
            assert resolve_session_context_type(conn, None) == "none"
            assert resolve_session_context_type(conn, "1") == "regular"
            assert resolve_session_context_type(conn, "0") == "system"
            for household_id in ("missing", "", "demo-household"):
                with pytest.raises(HTTPException) as exc:
                    resolve_session_context_type(conn, household_id)
                assert_http_status(exc, 403)
    finally:
        engine.dispose()


def test_schema_compatibility_shim_is_inert_on_canonical_postgresql_head():
    engine = _seed_regular_fixture()
    try:
        with engine.begin() as conn:
            before_columns = inspect(conn).get_columns("server_sessions")
            before_indexes = inspect(conn).get_indexes("server_sessions")
            before_rows = conn.execute(text("SELECT * FROM server_sessions ORDER BY id")).all()
            ensure_server_session_schema(conn)
            ensure_server_session_schema(conn)
            after_columns = inspect(conn).get_columns("server_sessions")
            after_indexes = inspect(conn).get_indexes("server_sessions")
            after_rows = conn.execute(text("SELECT * FROM server_sessions ORDER BY id")).all()
            assert [c["name"] for c in before_columns] == [c["name"] for c in after_columns]
            assert before_indexes == after_indexes
            assert before_rows == after_rows
            active_household = next(
                column for column in after_columns
                if column["name"] == "active_household_id"
            )
            assert active_household["nullable"] is True
    finally:
        engine.dispose()
