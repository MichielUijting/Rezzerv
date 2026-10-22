from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
import pytest

from app.api.server_session_routes import (
    SessionApiConfiguration,
    create_server_session_router,
)
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
    seed_household,
    seed_membership,
    seed_user,
)


def _runtime_schema_client():
    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        seed_household(conn, household_id='0', name='Systeem', context_type='system')
        seed_household(conn, household_id='1', name='Regulier', context_type='regular')
        seed_user(
            conn,
            user_id='u-admin',
            email='admin@rezzerv.local',
            password='Rezzerv123',
        )
        seed_membership(
            conn,
            membership_id='m-active',
            household_id='1',
            user_id='u-admin',
            email='ADMIN@REZZERV.LOCAL',
            role='owner',
        )

    app = FastAPI()
    app.include_router(
        create_server_session_router(
            engine,
            SessionApiConfiguration(cookie_secure=False, cookie_samesite="lax"),
        )
    )
    return TestClient(app), engine


def test_login_and_session_resolve_with_user_email_membership_schema():
    client, engine = _runtime_schema_client()
    try:
        login = client.post(
            "/api/auth/login",
            json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
        )

        assert login.status_code == 200
        assert login.json()["user"]["id"] == "u-admin"
        assert login.json()["active_household_id"] == "1"
        assert login.json()["role"] == "admin"
        assert client.get("/api/session").status_code == 200
    finally:
        engine.dispose()


@pytest.mark.parametrize('maintenance_state', ['draining', 'locked', 'verifying', 'blocked'])
def test_platform_admin_can_log_in_with_real_maintenance_write_barrier(maintenance_state):
    client, engine = _runtime_schema_client()
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO auth_platform_user_roles(user_id, role_key, active)
                VALUES ('u-admin', 'platform.platform_admin', TRUE)
            """))
            conn.execute(text("UPDATE maintenance_control SET state=:state WHERE id=1"),
                         {'state': maintenance_state})
        # No mocked session/role service and no maintenance-admin bypass. The
        # installed PostgreSQL statement triggers reject domain provisioning.
        login = client.post('/api/auth/login', json={
            'email': 'admin@rezzerv.local', 'password': 'Rezzerv123',
        })
        assert login.status_code == 200, login.text
        assert login.json()['active_household_id'] is None
        assert client.get('/api/session').status_code == 200
        with engine.connect() as conn:
            assert conn.execute(text('SELECT state FROM maintenance_control WHERE id=1')).scalar_one() == maintenance_state
    finally:
        # Restore only this expendable fixture's infrastructure singleton, so
        # the next fixture can perform its normal controlled reset.
        with engine.begin() as conn:
            conn.execute(text("UPDATE maintenance_control SET state='normal' WHERE id=1"))
        engine.dispose()


def test_removed_runtime_membership_is_not_accepted():
    client, engine = _runtime_schema_client()
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM auth_membership_roles
                WHERE household_id = '1' AND membership_id = 'm-active'
            """))
            conn.execute(text("""
                DELETE FROM household_memberships
                WHERE id = 'm-active'
            """))

        response = client.post(
            "/api/auth/login",
            json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Geen geldige accountcontext beschikbaar."
    finally:
        engine.dispose()
