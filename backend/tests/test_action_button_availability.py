"""Global Startpagina-action availability and ordering contracts on PostgreSQL."""
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
        flags.validate_home_action_order_schema(conn)
        conn.execute(text('DELETE FROM platform_home_action_order'))
        conn.execute(text('DELETE FROM platform_feature_flags'))
        conn.execute(text("DELETE FROM auth_audit_log WHERE action IN ('platform.action_button.updated', 'platform.action_button.order.updated', 'platform.functional_feature.updated')"))

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
            conn.execute(text('DELETE FROM platform_home_action_order'))
            conn.execute(text('DELETE FROM platform_feature_flags'))
            conn.execute(text("DELETE FROM auth_audit_log WHERE action IN ('platform.action_button.updated', 'platform.action_button.order.updated', 'platform.functional_feature.updated')"))
        engine.dispose()


def home_action_keys():
    return {key for key, definition in flags.FEATURE_FLAG_DEFINITIONS.items() if definition.get('home_tile_key')}


def test_product_projection_contains_startpage_actions_in_default_order(authority):
    engine, actor, _, client = authority
    actor['id'] = 'member'
    response = client.get('/api/action-buttons?household_id=ignored')
    assert response.status_code == 200
    items = response.json()['items']
    assert [item['key'] for item in items] == list(flags.HOME_ACTION_DEFAULT_ORDER)
    assert {item['key'] for item in items} == home_action_keys()
    assert all(set(item) == {'key', 'home_tile_key', 'enabled', 'sort_order'} for item in items)
    assert [item['sort_order'] for item in items] == list(range(len(items)))

    by_key = {item['key']: item for item in items}
    assert by_key[flags.FEATURE_GERECHTEN]['home_tile_key'] == 'recepten'
    assert by_key[flags.FEATURE_GERECHTEN]['enabled'] is False
    assert all(item['enabled'] is True for key, item in by_key.items() if key != flags.FEATURE_GERECHTEN)

    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM platform_feature_flags')).scalar_one() == 0
        assert conn.execute(text('SELECT count(*) FROM platform_home_action_order')).scalar_one() == 0


def test_superuser_management_targets_only_startpage_actions(authority):
    engine, actor, requested_permissions, client = authority
    actor['id'] = 'superuser'

    response = client.get('/api/platform/action-buttons')
    assert response.status_code == 200
    assert {item['key'] for item in response.json()['items']} == home_action_keys()
    assert requested_permissions[-1] == routes.FUNCTIONAL_FEATURES_MANAGE_PERMISSION

    key = flags.ACTION_HOME_WINKELEN
    response = client.put(f'/api/platform/action-buttons/{key}', json={'enabled': False})
    assert response.status_code == 200
    assert response.json()['item']['enabled'] is False
    assert response.json()['item']['home_tile_key'] == 'winkelen'

    response = client.put(f'/api/platform/action-buttons/{flags.FEATURE_GERECHTEN}', json={'enabled': True})
    assert response.status_code == 200
    assert response.json()['item']['home_tile_key'] == 'recepten'
    assert response.json()['item']['enabled'] is True

    assert client.put('/api/platform/action-buttons/external_product_search', json={'enabled': False}).status_code == 404
    assert client.put('/api/platform/action-buttons/action.kassa.open_camera', json={'enabled': False}).status_code == 404
    assert client.put('/api/platform/action-buttons/action.unknown', json={'enabled': False}).status_code == 404
    assert client.put(f'/api/platform/functional-features/{key}', json={'enabled': True}).status_code == 404
    assert client.put(f'/api/platform/feature-flags/{key}', json={'enabled': True}).status_code == 404

    with engine.connect() as conn:
        rows = conn.execute(text('SELECT flag_key, enabled FROM platform_feature_flags ORDER BY flag_key')).mappings().all()
    assert [dict(row) for row in rows] == [
        {'flag_key': key, 'enabled': False},
        {'flag_key': flags.FEATURE_GERECHTEN, 'enabled': True},
    ]


def test_reorder_is_global_atomic_persistent_and_audited(authority):
    engine, actor, requested_permissions, client = authority
    actor['id'] = 'superuser'
    default = list(flags.HOME_ACTION_DEFAULT_ORDER)
    moved = [flags.ACTION_HOME_VOORRAAD] + [key for key in default if key != flags.ACTION_HOME_VOORRAAD]

    response = client.put('/api/platform/action-buttons/order', json={'keys': moved})
    assert response.status_code == 200
    assert [item['key'] for item in response.json()['items']] == moved
    assert requested_permissions[-1] == routes.FUNCTIONAL_FEATURES_MANAGE_PERMISSION

    for reader in ['member', 'owner', 'superuser']:
        actor['id'] = reader
        product = client.get('/api/action-buttons').json()['items']
        assert [item['key'] for item in product] == moved
        assert [item['sort_order'] for item in product] == list(range(len(moved)))

    with engine.connect() as conn:
        stored = conn.execute(text('SELECT flag_key FROM platform_home_action_order ORDER BY sort_order')).scalars().all()
        audit = conn.execute(text("""
            SELECT actor_user_id, old_value, new_value, household_id
            FROM auth_audit_log
            WHERE action = 'platform.action_button.order.updated'
            ORDER BY created_at DESC LIMIT 1
        """)).mappings().one()
    assert list(stored) == moved
    assert audit['actor_user_id'] == 'superuser'
    assert json.loads(audit['old_value']) == {'keys': default}
    assert json.loads(audit['new_value']) == {'keys': moved}
    assert audit['household_id'] is None

    actor['id'] = 'superuser'
    assert client.put('/api/platform/action-buttons/order', json={'keys': moved[:-1]}).status_code == 400
    duplicate = moved[:-1] + [moved[0]]
    assert client.put('/api/platform/action-buttons/order', json={'keys': duplicate}).status_code == 400
    unknown = moved[:-1] + ['action.home.unknown']
    assert client.put('/api/platform/action-buttons/order', json={'keys': unknown}).status_code == 400

    with engine.connect() as conn:
        still_stored = conn.execute(text('SELECT flag_key FROM platform_home_action_order ORDER BY sort_order')).scalars().all()
    assert list(still_stored) == moved


def test_home_action_toggle_is_global_audited_and_noop_does_not_duplicate_audit(authority):
    engine, actor, _, client = authority
    key = flags.ACTION_HOME_VOORRAAD
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
            assert item['home_tile_key'] == 'voorraad'
        actor['id'] = 'superuser'

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT actor_user_id, action, object_id, old_value, new_value, household_id
            FROM auth_audit_log
            WHERE action = 'platform.action_button.updated' AND object_id = :key
            ORDER BY created_at
        """), {'key': key}).mappings().all()
    assert len(rows) == 2
    assert [json.loads(row['old_value']) for row in rows] == [{'enabled': True}, {'enabled': False}]
    assert [json.loads(row['new_value']) for row in rows] == [{'enabled': False}, {'enabled': True}]
    assert all(row['actor_user_id'] == 'superuser' for row in rows)
    assert all(row['household_id'] is None for row in rows)


def test_gerechten_management_uses_single_existing_functional_flag(authority):
    engine, actor, _, client = authority
    actor['id'] = 'superuser'
    response = client.put(f'/api/platform/action-buttons/{flags.FEATURE_GERECHTEN}', json={'enabled': True})
    assert response.status_code == 200

    actor['id'] = 'member'
    action_projection = client.get('/api/action-buttons').json()['items']
    gerechten_action = next(item for item in action_projection if item['key'] == flags.FEATURE_GERECHTEN)
    assert gerechten_action['key'] == flags.FEATURE_GERECHTEN
    assert gerechten_action['home_tile_key'] == 'recepten'
    assert gerechten_action['enabled'] is True
    assert isinstance(gerechten_action['sort_order'], int)
    assert client.get('/api/features').json()['features'][flags.FEATURE_GERECHTEN] is True

    with engine.connect() as conn:
        audits = conn.execute(text("""
            SELECT action, object_id FROM auth_audit_log
            WHERE object_id = :key ORDER BY created_at
        """), {'key': flags.FEATURE_GERECHTEN}).mappings().all()
    assert [dict(row) for row in audits] == [
        {'action': 'platform.functional_feature.updated', 'object_id': flags.FEATURE_GERECHTEN}
    ]
