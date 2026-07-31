from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api import authorization_membership_routes as routes
from app.services.authorization_foundation_service import ensure_authorization_foundation


def _client():
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
              ('u-owner', 'eigenaar@example.test'),
              ('u-member', 'lid@example.test'),
              ('u-outsider', 'buitenstaander@example.test')
        """))
        conn.execute(text("""
            INSERT INTO household_memberships(id, household_id, user_email, role, status) VALUES
              ('m-owner', 'h1', 'eigenaar@example.test', 'owner', 'active'),
              ('m-member', 'h1', 'lid@example.test', 'member', 'active'),
              ('m-outsider', 'h2', 'buitenstaander@example.test', 'owner', 'active')
        """))
        ensure_authorization_foundation(conn)
    routes.engine = engine
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app), engine


def _headers(email):
    return {"Authorization": f"Bearer rezzerv-dev-token::{email}"}


def test_missing_token_returns_401():
    client, _ = _client()
    response = client.get('/api/households/h1/authorization/members')
    assert response.status_code == 401


def test_household_outsider_is_denied():
    client, _ = _client()
    response = client.get(
        '/api/households/h1/authorization/members',
        headers=_headers('buitenstaander@example.test'),
    )
    assert response.status_code == 403


def test_owner_can_list_members_roles_and_permissions():
    client, _ = _client()
    headers = _headers('eigenaar@example.test')
    members = client.get('/api/households/h1/authorization/members', headers=headers)
    roles = client.get('/api/households/h1/authorization/roles', headers=headers)
    permissions = client.get('/api/households/h1/authorization/permissions', headers=headers)

    assert members.status_code == 200
    assert members.json()['total'] == 2
    assert {item['role_key'] for item in members.json()['items']} == {
        'huishouden.eigenaar', 'huishouden.lid'
    }

    assert roles.status_code == 200
    role_items = roles.json()['items']
    assert {item['role_key'] for item in role_items} == {
        'huishouden.eigenaar', 'huishouden.lid', 'huishouden.kijker'
    }
    owner_role = next(item for item in role_items if item['role_key'] == 'huishouden.eigenaar')
    viewer_role = next(item for item in role_items if item['role_key'] == 'huishouden.kijker')
    assert 'members.manage' in owner_role['permission_keys']
    assert 'inventory.view' in viewer_role['permission_keys']
    assert 'inventory.update' not in viewer_role['permission_keys']

    assert permissions.status_code == 200
    assert any(item['permission_key'] == 'members.manage' for item in permissions.json()['items'])


def test_member_cannot_manage_roles():
    client, _ = _client()
    response = client.put(
        '/api/households/h1/authorization/members/m-owner/role',
        headers=_headers('lid@example.test'),
        json={'role_key': 'huishouden.lid'},
    )
    assert response.status_code == 403
    assert response.json()['detail']['permission_key'] == 'members.manage'


def test_owner_can_change_member_to_viewer_and_audit_is_written():
    client, engine = _client()
    response = client.put(
        '/api/households/h1/authorization/members/m-member/role',
        headers=_headers('eigenaar@example.test'),
        json={'role_key': 'huishouden.kijker', 'reason': 'Alleen meekijken'},
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
    assert role == 'huishouden.kijker'
    assert action == 'autorisatie.huishoudrol.gewijzigd'


def test_owner_cannot_demote_self_without_transfer():
    client, _ = _client()
    response = client.put(
        '/api/households/h1/authorization/members/m-owner/role',
        headers=_headers('eigenaar@example.test'),
        json={'role_key': 'huishouden.lid'},
    )
    assert response.status_code == 400
    assert 'eigenaarschap' in str(response.json()['detail']).lower()


def test_individual_permission_override_is_disabled():
    client, _ = _client()
    response = client.put(
        '/api/households/h1/authorization/members/m-member/permissions/inventory.view',
        headers=_headers('eigenaar@example.test'),
        json={'effect': 'deny', 'reason': 'Tijdelijk'},
    )
    assert response.status_code == 400
    assert 'niet beschikbaar' in str(response.json()['detail']).lower()
