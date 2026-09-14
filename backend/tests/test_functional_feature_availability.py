"""TD-08: isolated global availability, permission partition and audit contracts."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import OperationalError

from app.api import platform_feature_flags_routes as routes
from app.services import platform_feature_flag_service as flags
from app.services import session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.testing.authorization_schema_fixture import install_authorization_schema


@pytest.fixture
def authority(monkeypatch):
    postgres_url = os.getenv('FUNCTIONAL_FEATURE_POSTGRESQL_TEST_URL')
    if postgres_url:
        engine = create_engine(postgres_url)
        # Explicitly opt in to a disposable, separately migrated test database.
        assert engine.url.database == 'rezzerv_functional_feature_test'
        assert engine.dialect.name == 'postgresql'
    else:
        engine = create_engine('sqlite://', poolclass=StaticPool,
                               connect_args={'check_same_thread': False})
    with engine.begin() as conn:
        if not postgres_url:
            install_authorization_schema(conn)
            conn.execute(text('''CREATE TABLE platform_feature_flags (
                flag_key TEXT PRIMARY KEY, enabled BOOLEAN NOT NULL,
                updated_by TEXT, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)'''))
        else:
            flags.validate_platform_feature_flag_schema(conn)
            conn.execute(text('DELETE FROM platform_feature_flags'))
            conn.execute(text('DELETE FROM auth_audit_log'))
            conn.execute(text('DELETE FROM auth_platform_user_roles'))
        ensure_authorization_foundation(conn)
        for user, role in [('superuser', 'platform.superuser'),
                           ('technical', 'platform.platform_admin'),
                           ('owner', 'platform.ip_owner')]:
            conn.execute(text('''INSERT INTO auth_platform_user_roles(user_id, role_key, active)
                VALUES (:user, :role, TRUE)'''), {'user': user, 'role': role})
    actor = {'id': 'superuser'}

    def session():
        if actor['id'] is None:
            raise HTTPException(status_code=401, detail='Geen geldige sessie')
        return SimpleNamespace(user_id=actor['id'], context_type='system')

    monkeypatch.setattr(routes, 'engine', engine)
    monkeypatch.setattr(session_request_context, 'engine', engine)
    monkeypatch.setattr(session_request_context, 'resolve_current_server_session', session)
    monkeypatch.setattr(routes, 'resolve_current_server_session', session)
    app = FastAPI()
    app.include_router(routes.router)
    try:
        with TestClient(app) as client:
            yield engine, actor, client
    finally:
        if postgres_url:
            # Leave no active IP-owner or feature rows for the next test module.
            with engine.begin() as conn:
                conn.execute(text('DELETE FROM platform_feature_flags'))
                conn.execute(text('DELETE FROM auth_audit_log'))
                conn.execute(text('DELETE FROM auth_platform_user_roles'))
        engine.dispose()


@pytest.mark.parametrize('user,functional,technical', [
    ('superuser', 200, 403), ('technical', 403, 200), ('owner', 200, 200),
    ('member', 403, 403), ('admin', 403, 403), (None, 401, 401),
])
def test_permission_partition_and_both_write_boundaries(authority, user, functional, technical):
    engine, actor, client = authority
    actor['id'] = user
    for path, key, expected in [
        ('functional-features', flags.FEATURE_GERECHTEN, functional),
        ('feature-flags', flags.FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH, technical),
    ]:
        assert client.get(f'/api/platform/{path}').status_code == expected
        response = client.put(f'/api/platform/{path}/{key}', json={'enabled': True})
        assert response.status_code == expected


@pytest.mark.parametrize('user', ['superuser', 'owner'])
def test_functional_endpoint_cannot_change_technical_or_unknown_keys(authority, user):
    engine, actor, client = authority
    actor['id'] = user
    for key in ['external_product_search', 'feature.unknown']:
        assert client.put(f'/api/platform/functional-features/{key}',
                          json={'enabled': False}).status_code == 404
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM platform_feature_flags')).scalar_one() == 0


@pytest.mark.parametrize('user', ['technical', 'owner'])
def test_technical_endpoint_cannot_change_functional_key(authority, user):
    _, actor, client = authority
    actor['id'] = user
    assert client.put('/api/platform/feature-flags/feature.gerechten',
                      json={'enabled': True}).status_code == 404
    assert [i['key'] for i in client.get('/api/platform/feature-flags').json()['items']] == [
        flags.FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH]


def test_default_off_read_projection_no_seed_or_household_override(authority):
    engine, actor, client = authority
    for user in ['member', 'superuser', 'technical', 'owner']:
        actor['id'] = user
        assert client.get('/api/features?household_id=0&enabled=true').json() == {
            'features': {flags.FEATURE_GERECHTEN: False}}
    actor['id'] = 'superuser'
    items = client.get('/api/platform/functional-features').json()['items']
    assert len(items) == 1 and items[0]['default_enabled'] is False
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM platform_feature_flags')).scalar_one() == 0
        assert flags.is_platform_feature_enabled(conn, flags.FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH)
        with pytest.raises(HTTPException) as exc:
            flags.require_platform_feature_enabled(conn, flags.FEATURE_GERECHTEN)
        assert exc.value.status_code == 503
    actor['id'] = None
    assert client.get('/api/features').status_code == 401


def test_global_toggle_persistence_audit_and_noop(authority):
    engine, actor, client = authority
    for enabled in [True, True, False]:
        actor['id'] = 'superuser'
        response = client.put('/api/platform/functional-features/feature.gerechten',
                              json={'enabled': enabled})
        assert response.status_code == 200
        assert response.json()['item']['enabled'] is enabled
        for user in ['member', 'superuser', 'owner']:
            actor['id'] = user
            assert client.get('/api/features').json()['features'][flags.FEATURE_GERECHTEN] is enabled
        with engine.connect() as conn:
            assert flags.is_platform_feature_enabled(conn, flags.FEATURE_GERECHTEN) is enabled
            if enabled:
                flags.require_platform_feature_enabled(conn, flags.FEATURE_GERECHTEN)
            assert flags.is_platform_feature_enabled(conn, flags.FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM auth_audit_log ORDER BY created_at")).mappings().all()
    assert len(rows) == 2
    for row, old, new in zip(rows, [False, True], [True, False]):
        assert row['actor_user_id'] == 'superuser'
        assert row['object_id'] == flags.FEATURE_GERECHTEN
        assert json.loads(row['old_value']) == {'enabled': old}
        assert json.loads(row['new_value']) == {'enabled': new}
        assert row['created_at'] and row['household_id'] is None


def test_audit_failure_rolls_back_feature_write(authority, monkeypatch):
    engine, _, _ = authority

    def fail(*args, **kwargs):
        raise RuntimeError('audit unavailable')

    monkeypatch.setattr(flags, 'write_authorization_audit', fail)
    with pytest.raises(RuntimeError):
        with engine.begin() as conn:
            flags.set_platform_feature_flag(conn, flags.FEATURE_GERECHTEN,
                                            enabled=True, updated_by='superuser')
    with engine.connect() as conn:
        assert flags.is_platform_feature_enabled(conn, flags.FEATURE_GERECHTEN) is False


def test_schema_failure_is_not_masked_by_default(authority):
    engine = create_engine('sqlite://')
    with engine.connect() as conn, pytest.raises(OperationalError):
        flags.is_platform_feature_enabled(conn, flags.FEATURE_GERECHTEN)
    engine.dispose()


def test_revocation_applies_to_next_request(authority):
    engine, _, client = authority
    assert client.get('/api/platform/functional-features').status_code == 200
    with engine.begin() as conn:
        conn.execute(text("UPDATE auth_platform_user_roles SET active = FALSE WHERE user_id = 'superuser'"))
    assert client.put('/api/platform/functional-features/feature.gerechten',
                      json={'enabled': True}).status_code == 403


def test_postgresql_concurrent_first_write_has_one_audited_transition(authority):
    engine, _, _ = authority
    if engine.dialect.name != 'postgresql':
        pytest.skip('Requires explicit disposable PostgreSQL test database')
    barrier = Barrier(2)

    def enable(actor):
        with engine.begin() as conn:
            barrier.wait(timeout=10)
            flags.set_platform_feature_flag(conn, flags.FEATURE_GERECHTEN,
                                            enabled=True, updated_by=actor)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(enable, ['superuser', 'owner']))
    with engine.connect() as conn:
        assert flags.is_platform_feature_enabled(conn, flags.FEATURE_GERECHTEN) is True
        rows = conn.execute(text('SELECT * FROM auth_audit_log')).mappings().all()
        assert len(rows) == 1
        assert json.loads(rows[0]['old_value']) == {'enabled': False}
        assert json.loads(rows[0]['new_value']) == {'enabled': True}
