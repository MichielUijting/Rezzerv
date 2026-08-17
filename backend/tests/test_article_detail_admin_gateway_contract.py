from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import HTTPException

from app.api.article_detail_admin_routes import (
    transfer_article_detail_inventory_admin_only,
    update_article_detail_admin_only,
    update_article_detail_settings_admin_only,
    mutate_article_detail_inventory_admin_only,
)


ARTICLE_ID = 'article-a'
INVENTORY_ID = 'inventory-a'


class FakePayload:
    def __init__(self, **data):
        self.data = data

    @classmethod
    def model_validate(cls, data):
        return cls(**dict(data or {}))


class FakeConnection:
    pass


class FakeEngine:
    @contextmanager
    def begin(self):
        yield FakeConnection()


def _build_main_endpoint(name, calls, *, inventory=False):
    def require_household_admin_context(authorization, requested_household_id=None):
        if authorization == 'Bearer member':
            raise HTTPException(status_code=403, detail='Alleen de beheerder van het huishouden mag deze actie uitvoeren')
        if authorization not in {'Bearer admin', 'Bearer owner'}:
            raise HTTPException(status_code=401, detail='Unauthorized')
        return {'active_household_id': 'household-a', 'display_role': 'admin'}

    namespace = {
        '__name__': 'app.main',
        'Payload': FakePayload,
        'calls': calls,
        'require_household_admin_context': require_household_admin_context,
    }
    if inventory:
        namespace.update({
            'engine': FakeEngine(),
            'fetch_inventory_row': lambda conn, inventory_id, household_id: {
                'id': inventory_id,
                'household_id': household_id,
                'household_article_id': ARTICLE_ID,
                'article_name': 'Testartikel',
            },
            'resolve_existing_inventory_household_article_id': lambda conn, household_id, article_name: ARTICLE_ID,
        })

    if name == 'patch':
        exec(
            "def endpoint(household_article_id: str, payload: Payload, authorization=None):\n"
            "    calls.append(('patch', household_article_id, payload.data, authorization))\n"
            "    return {'ok': True, 'kind': 'patch'}\n",
            namespace,
        )
    elif name == 'settings':
        exec(
            "def endpoint(household_article_id: str, payload: Payload, authorization=None):\n"
            "    calls.append(('settings', household_article_id, payload.data, authorization))\n"
            "    return {'ok': True, 'kind': 'settings'}\n",
            namespace,
        )
    elif name == 'inventory':
        exec(
            "def endpoint(payload: Payload, authorization=None):\n"
            "    calls.append(('inventory', payload.data, authorization))\n"
            "    return {'ok': True, 'kind': 'inventory'}\n",
            namespace,
        )
    elif name == 'transfer':
        exec(
            "def endpoint(payload: Payload, authorization=None):\n"
            "    calls.append(('transfer', payload.data, authorization))\n"
            "    return {'ok': True, 'kind': 'transfer'}\n",
            namespace,
        )
    else:
        raise AssertionError(name)

    return namespace['endpoint']


def _request_for(endpoint, path, method):
    route = SimpleNamespace(path=path, methods={method}, endpoint=endpoint)
    return SimpleNamespace(app=SimpleNamespace(routes=[route]))


def _assert_member_denied(callable_):
    try:
        callable_()
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError('Lid had door de Artikeldetail admin-gateway geblokkeerd moeten worden')


def test_patch_and_settings_are_admin_only_before_delegation():
    calls = []
    patch_endpoint = _build_main_endpoint('patch', calls)
    patch_request = _request_for(patch_endpoint, '/api/household-articles/{household_article_id}', 'PATCH')

    _assert_member_denied(lambda: update_article_detail_admin_only(
        ARTICLE_ID, patch_request, {'custom_name': 'Nieuw'}, 'Bearer member'
    ))
    assert calls == []

    result = update_article_detail_admin_only(
        ARTICLE_ID, patch_request, {'custom_name': 'Nieuw'}, 'Bearer admin'
    )
    assert result == {'ok': True, 'kind': 'patch'}
    assert calls == [('patch', ARTICLE_ID, {'custom_name': 'Nieuw'}, 'Bearer admin')]

    calls.clear()
    settings_endpoint = _build_main_endpoint('settings', calls)
    settings_request = _request_for(settings_endpoint, '/api/household-articles/{household_article_id}/settings', 'PUT')
    _assert_member_denied(lambda: update_article_detail_settings_admin_only(
        ARTICLE_ID, settings_request, {'notes': 'x'}, 'Bearer member'
    ))
    assert calls == []

    result = update_article_detail_settings_admin_only(
        ARTICLE_ID, settings_request, {'notes': 'x'}, 'Bearer owner'
    )
    assert result == {'ok': True, 'kind': 'settings'}
    assert calls == [('settings', ARTICLE_ID, {'notes': 'x'}, 'Bearer owner')]


def test_inventory_and_transfer_are_admin_only_and_article_scoped():
    calls = []
    inventory_endpoint = _build_main_endpoint('inventory', calls, inventory=True)
    inventory_request = _request_for(inventory_endpoint, '/api/inventory-events', 'POST')

    payload = {'inventory_id': INVENTORY_ID, 'quantity': 3, 'event_type': 'adjustment'}
    _assert_member_denied(lambda: mutate_article_detail_inventory_admin_only(
        ARTICLE_ID, inventory_request, payload, 'Bearer member'
    ))
    assert calls == []

    result = mutate_article_detail_inventory_admin_only(
        ARTICLE_ID, inventory_request, payload, 'Bearer admin'
    )
    assert result == {'ok': True, 'kind': 'inventory'}
    assert calls == [('inventory', payload, 'Bearer admin')]

    calls.clear()
    transfer_endpoint = _build_main_endpoint('transfer', calls, inventory=True)
    transfer_request = _request_for(transfer_endpoint, '/api/inventory-transfers', 'POST')
    transfer_payload = {'inventory_id': INVENTORY_ID, 'quantity': 1, 'to_space_id': 'space-b'}

    _assert_member_denied(lambda: transfer_article_detail_inventory_admin_only(
        ARTICLE_ID, transfer_request, transfer_payload, 'Bearer member'
    ))
    assert calls == []

    result = transfer_article_detail_inventory_admin_only(
        ARTICLE_ID, transfer_request, transfer_payload, 'Bearer owner'
    )
    assert result == {'ok': True, 'kind': 'transfer'}
    assert calls == [('transfer', transfer_payload, 'Bearer owner')]


def run_contract() -> None:
    test_patch_and_settings_are_admin_only_before_delegation()
    test_inventory_and_transfer_are_admin_only_and_article_scoped()
    print('ARTICLE_DETAIL_ADMIN_GATEWAY_GREEN')


if __name__ == '__main__':
    run_contract()
