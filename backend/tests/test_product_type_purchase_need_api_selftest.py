from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    client = TestClient(app)
    response = client.get('/api/households/1/product-type-purchase-needs')
    _assert(response.status_code == 200, f'Onverwachte statuscode: {response.status_code}')
    payload = response.json()
    _assert(payload.get('basis') == 'product_type', 'API-basis is niet Producttype')
    _assert(payload.get('need_source') == 'product_type_almost_out_decision', 'Onjuiste behoeftebron')
    _assert(payload.get('article_policy_fallback') is False, 'Artikelgebonden fallback is actief')
    _assert(payload.get('concrete_article_selection_deferred') is True, 'Concrete artikelselectie is niet uitgesteld')
    _assert(payload.get('read_only') is True, 'API moet read-only zijn')
    _assert(payload.get('mutates_inventory') is False, 'API mag voorraad niet muteren')
    _assert(payload.get('mutates_purchase_list') is False, 'API mag inkooplijst niet muteren')
    _assert(isinstance(payload.get('items'), list), 'items ontbreekt')
    _assert(isinstance(payload.get('projection_exceptions'), list), 'projectie-uitzonderingen ontbreken')
    print('PASS product_type_purchase_need_api_source')
    print('PASS product_type_purchase_need_api_contract')
    print('PRODUCT_TYPE_PURCHASE_NEED_API_GREEN')


if __name__ == '__main__':
    main()
