from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api import authorization_membership_routes as routes
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.server_session_service import ServerSessionContext


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
        role='owner' if email != 'member@example.test' else 'member',
        session_version=1,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    )


def _client(email: str = 'admin@example.test', household_id: str = 'h1', *, authenticated: bool = True):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                user_email TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            INSERT INTO app_users(id, email) VALUES
              ('u-admin', 'admin@example.test'),
              ('u-member', 'member@example.test'),
              ('u-outsider', 'outsider@example.test')
        """))
        conn.execute(text("""
            INSERT INTO household_memberships(id, household_id, user_email, role, status) VALUES
              ('m-admin', 'h1', 'admin@example.test', 'owner', 'active'),
              ('m-member', 'h1', 'member@example.test', 'member', 'active'),
              ('m-outsider', 'h2', 'outsider@example.test', 'owner', 'active')
        """))
        ensure_authorization_foundation(conn)
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
    client, _ = _client(authenticated=False)
    response = client.get('/api/households/h1/authorization/members')
    assert response.status_code == 401


def test_bearer_without_session_is_rejected_on_read_routes():
    client, _ = _client(authenticated=False)
    headers = _headers()
    for path in (
        '/api/households/h1/authorization/members',
        '/api/households/h1/authorization/roles',
        '/api/households/h1/authorization/permissions',
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 401


def test_bearer_without_session_is_rejected_on_mutation_route():
    client, _ = _client(authenticated=False)
    response = client.put(
        '/api/households/h1/authorization/members/m-member/role',
        headers=_headers(),
        json={'role_key': 'household.advanced_member'},
    )
    assert response.status_code == 401


def test_household_outsider_is_denied():
    client, _ = _client('outsider@example.test', 'h2')
    response = client.get('/api/households/h1/authorization/members')
    assert response.status_code == 403


def test_admin_can_list_members_roles_and_permissions():
    client, _ = _client()
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
    assert {item['role_key'] for item in role_items} == {
        'household.viewer',
        'household.member',
        'household.advanced_member',
        'household.admin',
        'household.owner',
        'household.frontteam',
    }
    admin_role = next(item for item in role_items if item['role_key'] == 'household.admin')
    viewer_role = next(item for item in role_items if item['role_key'] == 'household.viewer')
    assert 'permissions.manage' in admin_role['permission_keys']
    assert 'catalog.update' not in admin_role['permission_keys']
    assert 'gpc.update' in admin_role['permission_keys']
    assert 'inventory.view' in viewer_role['permission_keys']
    assert 'inventory.update' not in viewer_role['permission_keys']
    assert permissions.status_code == 200
    assert any(item['permission_key'] == 'permissions.manage' for item in permissions.json()['items'])


def test_member_cannot_manage_roles():
    client, _ = _client('member@example.test', 'h1')
    response = client.put(
        '/api/households/h1/authorization/members/m-admin/role',
        json={'role_key': 'household.member'},
    )
    assert response.status_code == 403
    assert response.json()['detail']['permission_key'] == 'members.manage'


def test_admin_can_change_member_role_and_audit_is_written():
    client, engine = _client()
    response = client.put(
        '/api/households/h1/authorization/members/m-member/role',
        json={'role_key': 'household.advanced_member', 'reason': 'Meer mogelijkheden'},
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
    assert role == 'household.advanced_member'
    assert action == 'authorization.membership_role.updated'


def test_last_admin_demotion_returns_409():
    client, _ = _client()
    response = client.put(
        '/api/households/h1/authorization/members/m-admin/role',
        json={'role_key': 'household.member'},
    )
    assert response.status_code == 409


def test_override_can_be_created_listed_and_deleted():
    client, _ = _client()
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


def test_platform_permission_cannot_be_assigned_in_household_scope():
    client, _ = _client()
    response = client.put(
        '/api/households/h1/authorization/members/m-member/permissions/platform.audit.view',
        json={'effect': 'allow'},
    )
    assert response.status_code == 400
