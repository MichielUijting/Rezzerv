from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api import authorization_membership_routes as routes
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.server_session_service import ServerSessionContext
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
    seed_household,
    seed_user_membership,
)


USER_IDS = {
    'admin@example.test': 'u-admin',
    'member@example.test': 'u-member',
    'outsider@example.test': 'u-outsider',
}


def _session_context(email: str, household_id: str) -> ServerSessionContext:
    now = datetime.now(timezone.utc)
    return ServerSessionContext(
        session_id='test-session',
        user_id=USER_IDS[email],
        email=email,
        active_household_id=household_id,
        context_type='regular',
        role='owner' if email != 'member@example.test' else 'member',
        session_version=1,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )


def _client(email: str = 'admin@example.test', household_id: str = 'h1', *, authenticated: bool = True):
    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        seed_household(conn, household_id='h1', name='Huishouden 1')
        seed_household(conn, household_id='h2', name='Huishouden 2')
        seed_user_membership(
            conn,
            household_id='h1',
            user_id='u-admin',
            email='admin@example.test',
            password='RouteTestAdmin123!',
            membership_id='m-admin',
            role='owner',
        )
        seed_user_membership(
            conn,
            household_id='h1',
            user_id='u-member',
            email='member@example.test',
            password='RouteTestMember123!',
            membership_id='m-member',
            role='member',
        )
        seed_user_membership(
            conn,
            household_id='h2',
            user_id='u-outsider',
            email='outsider@example.test',
            password='RouteTestOutsider123!',
            membership_id='m-outsider',
            role='owner',
        )
    routes.engine = engine
    if authenticated:
        context = _session_context(email, household_id)
        routes.resolve_current_server_session = lambda: context
    else:
        def missing_session():
            raise HTTPException(status_code=401, detail='Geen geldige sessie')
        routes.resolve_current_server_session = missing_session
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app), engine


def _headers(email: str = 'admin@example.test'):
    return {"Authorization": f"Bearer rezzerv-dev-token::{email}"}


def test_missing_session_returns_401():
    client, engine = _client(authenticated=False)
    try:
        response = client.get('/api/households/h1/authorization/members')
        assert response.status_code == 401
    finally:
        engine.dispose()


def test_bearer_without_session_is_rejected_on_read_routes():
    client, engine = _client(authenticated=False)
    try:
        headers = _headers()
        for path in (
            '/api/households/h1/authorization/members',
            '/api/households/h1/authorization/roles',
            '/api/households/h1/authorization/permissions',
        ):
            response = client.get(path, headers=headers)
            assert response.status_code == 401
    finally:
        engine.dispose()


def test_bearer_without_session_is_rejected_on_mutation_route():
    client, engine = _client(authenticated=False)
    try:
        response = client.put(
            '/api/households/h1/authorization/members/m-member/role',
            headers=_headers(),
            json={'role_key': 'household.advanced_member'},
        )
        assert response.status_code == 401
    finally:
        engine.dispose()


def test_household_outsider_is_denied():
    client, engine = _client('outsider@example.test', 'h2')
    try:
        response = client.get('/api/households/h1/authorization/members')
        assert response.status_code == 403
    finally:
        engine.dispose()


def test_admin_can_list_members_roles_and_permissions():
    client, engine = _client()
    try:
        members = client.get('/api/households/h1/authorization/members')
        roles = client.get('/api/households/h1/authorization/roles')
        permissions = client.get('/api/households/h1/authorization/permissions')
        assert members.status_code == 200
        assert members.json()['total'] == 2
        assert {item['role_key'] for item in members.json()['items']} == {
            'household.admin', 'household.member'
        }
        assert roles.status_code == 200
        role_items = roles.json()['items']
        assert [item['role_key'] for item in role_items] == [
            'household.member',
            'household.admin',
            'household.owner',
            'household.frontteam',
        ]
        assert [item['name'] for item in role_items] == [
            'Lid',
            'Beheerder',
            'Superuser',
            'Frontteamlid',
        ]
        admin_role = next(item for item in role_items if item['role_key'] == 'household.admin')
        assert 'permissions.manage' in admin_role['permission_keys']
        assert 'catalog.update' not in admin_role['permission_keys']
        assert 'gpc.update' in admin_role['permission_keys']
        assert permissions.status_code == 200
        assert any(item['permission_key'] == 'permissions.manage' for item in permissions.json()['items'])
    finally:
        engine.dispose()


def test_member_cannot_manage_roles():
    client, engine = _client('member@example.test', 'h1')
    try:
        response = client.put(
            '/api/households/h1/authorization/members/m-admin/role',
            json={'role_key': 'household.member'},
        )
        assert response.status_code == 403
        assert response.json()['detail']['permission_key'] == 'members.manage'
    finally:
        engine.dispose()


def test_admin_can_change_member_role_and_audit_is_written():
    client, engine = _client()
    try:
        response = client.put(
            '/api/households/h1/authorization/members/m-member/role',
            json={'role_key': 'household.admin', 'reason': 'Huishoudbeheer'},
        )
        assert response.status_code == 200
        with engine.begin() as conn:
            role = conn.execute(text("""
                SELECT role_key FROM auth_membership_roles
                WHERE household_id = 'h1' AND membership_id = 'm-member'
            """)).scalar()
            action = conn.execute(text("""
                SELECT action FROM auth_audit_log
                WHERE object_id = 'm-member'
            """)).scalar()
            legacy_role = conn.execute(text("""
                SELECT role FROM household_memberships WHERE id = 'm-member'
            """)).scalar()
        assert role == 'household.admin'
        assert legacy_role == 'admin'
        assert action == 'authorization.membership_role.updated'
    finally:
        engine.dispose()


def test_admin_cannot_assign_legacy_or_special_role():
    client, engine = _client()
    try:
        for role_key in (
            'household.viewer',
            'household.advanced_member',
            'household.owner',
            'household.frontteam',
        ):
            response = client.put(
                '/api/households/h1/authorization/members/m-member/role',
                json={'role_key': role_key},
            )
            assert response.status_code == 400

        with engine.begin() as conn:
            role = conn.execute(text("""
                SELECT role_key FROM auth_membership_roles
                WHERE household_id = 'h1' AND membership_id = 'm-member'
            """)).scalar()
        assert role == 'household.member'
    finally:
        engine.dispose()


def test_last_admin_demotion_returns_409():
    client, engine = _client()
    try:
        response = client.put(
            '/api/households/h1/authorization/members/m-admin/role',
            json={'role_key': 'household.member'},
        )
        assert response.status_code == 409
    finally:
        engine.dispose()


def test_override_can_be_created_listed_and_deleted():
    client, engine = _client()
    try:
        created = client.put(
            '/api/households/h1/authorization/members/m-member/permissions/inventory.view',
            json={'effect': 'deny', 'reason': 'Tijdelijk'},
        )
        assert created.status_code == 200
        members = client.get('/api/households/h1/authorization/members')
        target = next(item for item in members.json()['items'] if item['membership_id'] == 'm-member')
        assert target['permission_overrides'][0]['effect'] == 'deny'
        deleted = client.delete(
            '/api/households/h1/authorization/members/m-member/permissions/inventory.view',
        )
        assert deleted.status_code == 200
        missing = client.delete(
            '/api/households/h1/authorization/members/m-member/permissions/inventory.view',
        )
        assert missing.status_code == 404
    finally:
        engine.dispose()


def test_platform_permission_cannot_be_assigned_in_household_scope():
    client, engine = _client()
    try:
        response = client.put(
            '/api/households/h1/authorization/members/m-member/permissions/platform.audit.view',
            json={'effect': 'allow'},
        )
        assert response.status_code == 400
    finally:
        engine.dispose()
