"""Login identity must not provision domain data while maintenance is closed.

Focused unit coverage; the runtime-membership suite exercises real PostgreSQL.
"""
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException
from app.api import server_session_routes as routes


@pytest.fixture
def identity():
    conn = MagicMock()
    conn.dialect.name = 'postgresql'
    account = {'user_id': 'maintenance-admin', 'email': 'admin@example.test',
               'password': 'test-only-password', 'password_hash': None}
    accounts = MagicMock()
    accounts.mappings.return_value.all.return_value = [account]
    state = MagicMock()
    state.scalar_one.return_value = 'locked'
    conn.execute.side_effect = [accounts, state]
    with patch.object(routes, 'inspect') as inspector, \
         patch.object(routes, 'ensure_frontteam_household_for_session_runtime') as provision, \
         patch.object(routes, 'resolve_active_platform_role_keys', return_value=frozenset({'platform.platform_admin'})), \
         patch.object(routes, 'membership_user_join_condition', return_value=''), \
         patch.object(routes, 'membership_active_condition', return_value=''), \
         patch.object(routes, 'membership_id_expression', return_value=''):
        inspector.return_value.get_columns.return_value = [{'name': 'password_hash'}]
        yield conn, state, provision


@pytest.mark.parametrize('state_name', ['draining', 'locked', 'verifying', 'blocked'])
def test_admin_identity_remains_available_without_domain_provisioning(identity, state_name):
    conn, state, provision = identity
    state.scalar_one.return_value = state_name
    provision.side_effect = AssertionError('domain provisioning forbidden')
    result = routes._resolve_login_identity(conn, 'admin@example.test', 'test-only-password')
    assert result['user_id'] == 'maintenance-admin'
    assert result['active_household_id'] is None
    assert result['platform_system_context'] is False
    provision.assert_not_called()
    assert 'FOR SHARE' in str(conn.execute.call_args_list[1].args[0])


@pytest.mark.parametrize('state_name', ['normal', 'announced'])
def test_existing_household_projection_preserved_before_maintenance(identity, state_name):
    conn, state, provision = identity
    state.scalar_one.return_value = state_name
    routes._resolve_login_identity(conn, 'admin@example.test', 'test-only-password')
    provision.assert_called_once_with(conn)


def test_invalid_password_never_reaches_maintenance_or_provisioning(identity):
    conn, _, provision = identity
    with pytest.raises(HTTPException) as error:
        routes._resolve_login_identity(conn, 'admin@example.test', 'wrong-password')
    assert error.value.status_code == 401
    assert conn.execute.call_count == 1
    provision.assert_not_called()


def test_unknown_maintenance_state_fails_closed(identity):
    conn, state, provision = identity
    state.scalar_one.return_value = 'unknown'
    with pytest.raises(ValueError):
        routes._resolve_login_identity(conn, 'admin@example.test', 'test-only-password')
    provision.assert_not_called()


def test_missing_maintenance_authority_fails_closed(identity):
    conn, state, provision = identity
    state.scalar_one.side_effect = RuntimeError('missing authority')
    with pytest.raises(RuntimeError):
        routes._resolve_login_identity(conn, 'admin@example.test', 'test-only-password')
    provision.assert_not_called()
