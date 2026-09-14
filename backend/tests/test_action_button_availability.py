"""Global action-button availability contracts on the migrated PostgreSQL authority."""
import json
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.api import platform_feature_flags_routes as routes
from app.services import platform_feature_flag_service as flags


@pytest.fixture
def authority(monkeypatch):
    postgres_url = os.getenv('FUNCTIONAL_FEATURE_POSTGRESQL_TEST_URL')
    if not postgres_url:
        pytest.skip('Requires explicit disposable PostgreSQL test database')

    engine = create_engine(postgres_url)
    assert engine.url.database == 'rezzerv_functional_feature_test'
    assert engine.dialect.name == 'postgresql'

    with engine.begin() as conn:
        flags.validate_platform_feature_flag_schema(conn)
        conn.execute(text('DELETE FROM platform_feature_flags'))
        conn.execute(text("DELETE FROM auth_audit_log WHERE action = 'platform.action_button.updated'"))

    actor = {'id': 'superuser'}
    requested_permissions = []

    def session():
        if actor['id'] is None:
            raise HTTPException(status_code=401, detail='Geen geldige sessie')
        return SimpleNamespace(user_id=actor['id'], context_type='system')

    def require_permission(permission):
        requested_permissions.append(permission)
        if actor['id'] not in {'superuser', 'owner'}:
            raise HTTPException(status_code=403, detail='Niet toegestaan')
        return session()

    monkeypatch.setattr(routes, 'engine', engine)
    monkeypatch.setattr(routes, 'resolve_current_server_session', session)
    monkeypatch.setattr(routes, 'require_platform_permission_from_session', require_permission)

    app = FastAPI()
    app.include_router(routes.router)
    try:
        with TestClient(app) as client:
            yield engine, actor, requested_permissions, client
    finally:
        with engine.begin() as conn:
            conn.execute(text('DELETE FROM platform_feature_flags'))
            conn.execute(text("DELETE FROM auth_audit_log WHERE action = 'platform.action_button.updated'"))
        engine.dispose()


def action_keys():
    return {
        key for key, definition in flags.FEATURE_FLAG_DEFINITIONS.items()
        if definition.get('category') == 'action_button'
    }


def test_product_projection_defaults_all_registered_actions_on_without_seeding(authority):
    engine, actor, _, client = authority
    actor['id'] = 'member'
    response = client.get('/api/action-buttons?household_id=ignored')
    assert response.status_code == 200
    items = response.json()['items']
    assert {item['key'] for item in items} == action_keys()
    assert items and all(item['enabled'] is True for item in items)
    assert all(set(item) == {'key', 'test_id', 'match_text', 'enabled'} for item in items)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM platform_feature_flags')).scalar_one() == 0


def test_superuser_management_uses_functional_permission_and_is_category_closed(authority):
    engine, actor, requested_permissions, client = authority
    actor['id'] = 'superuser'

    response = client.get('/api/platform/action-buttons')
    assert response.status_code == 200
    assert {item['key'] for item in response.json()['items']} == action_keys()
    assert requested_permissions[-1] == routes.FUNCTIONAL_FEATURES_MANAGE_PERMISSION

    key = flags.ACTION_SHOPPING_COMPLETE
    response = client.put(f'/api/platform/action-buttons/{key}', json={'enabled': False})
    assert response.status_code == 200
    assert response.json()['item']['enabled'] is False
    assert requested_permissions[-1] == routes.FUNCTIONAL_FEATURES_MANAGE_PERMISSION

    assert client.put('/api/platform/action-buttons/feature.gerechten', json={'enabled': False}).status_code == 404
    assert client.put('/api/platform/action-buttons/external_product_search', json={'enabled': False}).status_code == 404
    assert client.put('/api/platform/action-buttons/action.unknown', json={'enabled': False}).status_code == 404
    assert client.put(f'/api/platform/functional-features/{key}', json={'enabled': True}).status_code == 404
    assert client.put(f'/api/platform/feature-flags/{key}', json={'enabled': True}).status_code == 404

    with engine.connect() as conn:
        rows = conn.execute(text('SELECT flag_key, enabled FROM platform_feature_flags ORDER BY flag_key')).mappings().all()
    assert [dict(row) for row in rows] == [{'flag_key': key, 'enabled': False}]


def test_action_toggle_is_global_audited_and_noop_does_not_duplicate_audit(authority):
    engine, actor, _, client = authority
    key = flags.ACTION_INVENTORY_ADD_INCIDENTAL_PURCHASE
    actor['id'] = 'superuser'

    for enabled in [False, False, True]:
        response = client.put(f'/api/platform/action-buttons/{key}', json={'enabled': enabled})
        assert response.status_code == 200
        assert response.json()['item']['enabled'] is enabled
        for reader in ['member', 'superuser', 'owner']:
            actor['id'] = reader
            projection = client.get('/api/action-buttons').json()['items']
            item = next(item for item in projection if item['key'] == key)
            assert item['enabled'] is enabled
        actor['id'] = 'superuser'

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT actor_user_id, action, object_id, old_value, new_value, household_id
            FROM auth_audit_log
            WHERE action = 'platform.action_button.updated'
            ORDER BY created_at
        """)).mappings().all()

    assert len(rows) == 2
    assert [json.loads(row['old_value']) for row in rows] == [{'enabled': True}, {'enabled': False}]
    assert [json.loads(row['new_value']) for row in rows] == [{'enabled': False}, {'enabled': True}]
    assert all(row['actor_user_id'] == 'superuser' for row in rows)
    assert all(row['object_id'] == key for row in rows)
    assert all(row['household_id'] is None for row in rows)
