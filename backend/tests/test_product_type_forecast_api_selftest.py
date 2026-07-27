from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    client = TestClient(app)
    response = client.get('/api/households/1/product-type-forecast')
    _assert(response.status_code == 200, f'onverwachte status: {response.status_code}')
    payload = response.json()
    _assert(payload.get('basis') == 'product_type_snapshot', 'prognosebasis onjuist')
    _assert(payload.get('history_source') == 'product_type_quantity_events', 'historiebron onjuist')
    _assert(payload.get('inventory_source') == 'product_type_inventory_projection', 'voorraadbron onjuist')
    _assert(payload.get('historical_membership_recalculated') is False, 'historische koppelingen mogen niet worden herberekend')
    _assert(payload.get('article_policy_fallback') is False, 'artikelgebonden fallback is niet toegestaan')
    _assert(payload.get('read_only') is True, 'prognose-API moet read-only zijn')
    _assert(payload.get('mutates_inventory') is False, 'prognose-API mag voorraad niet muteren')
    _assert(isinstance(payload.get('items'), list), 'prognose-items ontbreken')
    _assert(isinstance(payload.get('projection_exceptions'), list), 'projectie-uitzonderingen ontbreken')
    print('PASS product_type_forecast_api_contract')
    print('PRODUCT_TYPE_FORECAST_API_GREEN')


if __name__ == '__main__':
    main()
