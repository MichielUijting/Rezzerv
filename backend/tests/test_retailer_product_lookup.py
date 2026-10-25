"""Synthetic guest catalog contracts: no private account, network, or database."""
import json
from types import SimpleNamespace

import pytest

from app.services import retailer_product_lookup as retail
from app.services import external_article_search_service as service

GTIN = '8718452504435'
OTHER = '8720326035617'


def item(provider='ah', code='123'):
    return {'receipt_item_id': 'receipt-table-line:synthetic', 'retailer_code': provider,
            'receipt_line_text': 'AH Halfvolle melk' if provider == 'ah' else 'Jumbo Halfvolle melk',
            'external_article_code': code}


def ah_transport(*, hq=123, webshop=987, returned_id=987, barcode=GTIN, title='AH Halfvolle melk', brand='AH'):
    calls = []
    def transport(provider, path, payload=None, **kwargs):
        calls.append((provider, path, payload, kwargs))
        if 'anonymous' in path:
            return {'access_token': 'synthetic-guest'}
        if 'search/v2' in path:
            return {'products': [{'hqId': hq, 'webshopId': webshop, 'title': title, 'brand': brand, 'salesUnitSize': '1 l'}]}
        assert payload['variables'] == {'id': webshop}
        return {'data': {'product': {'id': returned_id, 'title': title, 'tradeItem': {'gtin': barcode}}}}
    return transport, calls


def test_ah_receipt_hqid_never_becomes_webshop_id():
    transport, calls = ah_transport()
    result = retail.lookup_retailer_products(item(), transport)
    assert result['status'] == 'barcode_found'
    assert result['candidates'][0]['gtin'] == GTIN
    assert result['candidates'][0]['receipt_code_match'] is True
    assert calls[-1][2]['variables'] == {'id': 987}
    assert 'hqId' not in json.dumps(calls[-1][2])
    assert result['candidates'][0]['quantity'] == '1 l'


def test_ah_different_identifier_namespace_remains_suggestion():
    transport, _ = ah_transport()
    result = retail.lookup_retailer_products(item(code='987'), transport)
    assert result['status'] == 'name_suggestions'
    assert result['candidates'][0]['receipt_code_match'] is False


@pytest.mark.parametrize('kwargs', [{'returned_id': 999}, {'barcode': '8718452504436'},
    {'title': 'AH Volle melk'}, {'title': 'Campina Halfvolle melk', 'brand': 'Campina'}])
def test_ah_identity_variant_brand_and_checkdigit_are_enforced(kwargs):
    transport, _ = ah_transport(**kwargs)
    assert retail.lookup_retailer_products(item(), transport)['candidates'] == []


def test_ah_bad_guest_auth_and_raw_exception_do_not_leak_credentials():
    result = retail.lookup_retailer_products(item(), lambda *args, **kwargs: {'access_token': 123})
    assert result['status'] == 'unavailable'
    assert result['errors'] == ['guest_auth_invalid']


def jumbo_transport(*, denied=True, returned_sku='123PAK', name='Jumbo Halfvolle melk', barcode=GTIN, duplicate=False):
    calls = []
    def transport(provider, path, payload=None, **kwargs):
        calls.append((provider, path, payload))
        if path.startswith('/producten/?'):
            return '<a href="/producten/melk-123PAK">Melk</a>'
        if path == '/api/graphql':
            if denied:
                raise retail.CatalogError('http_401')
            return {'data': {'product': {'sku': returned_sku, 'title': name, 'brand': 'Jumbo', 'ean': barcode}}}
        p = {'@type': 'Product', 'sku': returned_sku, 'name': name, 'gtin13': barcode}
        if duplicate:
            p = [p, p]
        return '<script type="application/ld+json">' + json.dumps(p) + '</script>'
    return transport, calls


def test_jumbo_api_denial_falls_back_to_public_exact_sku():
    transport, calls = jumbo_transport()
    result = retail.lookup_retailer_products(item('jumbo', ''), transport)
    assert result['status'] == 'name_suggestions'
    assert result['candidates'][0]['gtin'] == GTIN
    assert len(calls) == 3


def test_jumbo_api_sku_matches_receipt_only_if_identical():
    transport, _ = jumbo_transport(denied=False)
    result = retail.lookup_retailer_products(item('jumbo', '123PAK'), transport)
    assert result['status'] == 'barcode_found'


@pytest.mark.parametrize('kwargs', [{'returned_sku': '999PAK'}, {'name': 'Jumbo Volle melk'},
                                   {'barcode': '8718452504436'}, {'duplicate': True}])
def test_jumbo_page_guard(kwargs):
    transport, _ = jumbo_transport(**kwargs)
    assert retail.lookup_retailer_products(item('jumbo', ''), transport)['candidates'] == []


def test_catalog_detail_error_keeps_other_valid_products():
    def transport(provider, path, payload=None, **kwargs):
        if 'anonymous' in path: return {'access_token': 'synthetic'}
        if 'search/v2' in path:
            return {'products': [{'hqId': 123, 'webshopId': 987, 'title': 'AH Halfvolle melk', 'brand': 'AH'},
                                 {'hqId': 456, 'webshopId': 999, 'title': 'AH Halfvolle melk', 'brand': 'AH'}]}
        if payload['variables']['id'] == 987: raise retail.CatalogError('http_503')
        return {'data': {'product': {'id': 999, 'title': 'AH Halfvolle melk', 'tradeItem': {'gtin': GTIN}}}}
    result = retail.lookup_retailer_products(item(), transport)
    assert len(result['candidates']) == 1
    assert result['status'] == 'name_suggestions'


def test_conflicting_receipt_evidence_never_becomes_exact():
    def transport(provider, path, payload=None, **kwargs):
        if 'anonymous' in path: return {'access_token': 'synthetic'}
        if 'search/v2' in path:
            return {'products': [{'hqId': 123, 'webshopId': n, 'title': 'AH Halfvolle melk', 'brand': 'AH'} for n in (987, 999)]}
        n = payload['variables']['id']
        return {'data': {'product': {'id': n, 'title': 'AH Halfvolle melk', 'tradeItem': {'gtin': GTIN if n == 987 else OTHER}}}}
    result = retail.lookup_retailer_products(item(), transport)
    assert result['status'] == 'conflicting_barcodes'
    assert len(result['candidates']) == 2


@pytest.mark.parametrize('provider,path,payload,token', [
    ('ah', 'https://evil.test/graphql', {'query': retail.AH_QUERY}, ''),
    ('jumbo', '/api/graphql', {'query': 'mutation AddCart{}'}, ''),
    ('ah', '/user/login', {}, ''),
    ('jumbo', '/producten/', None, 'private'),
    ('jumbo', 'http://www.jumbo.com/producten/', None, ''),
    ('ah', 'https://api.ah.nl:999/graphql', {'query': retail.AH_QUERY}, ''),
])
def test_transport_rejects_mutation_login_cross_host_and_token_leak(provider, path, payload, token):
    transport = retail.GuestTransport()
    with pytest.raises(retail.CatalogError):
        transport(provider, path, payload, token=token)
    assert transport.calls == 0


def test_transport_request_budget_and_response_size(monkeypatch):
    transport = retail.GuestTransport()
    transport.calls = 20
    with pytest.raises(retail.CatalogError, match='budget_exhausted'):
        transport('jumbo', '/producten/')
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, maximum): return b'x' * maximum
    transport = retail.GuestTransport()
    transport.opener = SimpleNamespace(open=lambda *args, **kwargs: Response())
    with pytest.raises(retail.CatalogError, match='response_too_large'):
        transport('jumbo', '/producten/')


def candidate(code=GTIN, exact=False):
    return {'gtin': code, 'product_name': 'AH Halfvolle melk', 'brand': 'AH', 'quantity': '1 l',
            'source': 'Albert Heijn', 'source_url': 'https://www.ah.nl/producten/product/wi987',
            'receipt_code_match': exact}


def service_fixture(monkeypatch, status, candidates):
    monkeypatch.setattr(service.off, 'resolve_receipt_item', lambda _: item())
    monkeypatch.setattr(service, 'lookup_retailer_products', lambda _: {
        'status': status, 'source': 'Albert Heijn', 'candidates': candidates, 'errors': []})


def test_exact_result_uses_off_gtin_not_name_and_never_writes(monkeypatch):
    service_fixture(monkeypatch, 'barcode_found', [candidate(exact=True)])
    called = []
    def exact(gtin):
        called.append(gtin)
        return {'status': 'found', 'product': {'gtin': gtin, 'product_name': 'AH Halfvolle melk'}}
    monkeypatch.setattr(service.off, 'lookup_off_product_by_gtin', exact)
    monkeypatch.setattr(service.off, 'search_off_candidates_for_item', lambda *a: pytest.fail('unexpected fuzzy lookup'))
    result = service.search_article_candidates({'receipt_item_id': 'synthetic', 'retailer_code': 'evil'})
    assert called == [GTIN]
    assert result['results'][0]['source'] == 'Albert Heijn + Open Food Facts'
    for flag in ('mutated', 'creates_global_product', 'creates_household_article', 'creates_inventory_event', 'creates_external_candidate'):
        assert result[flag] is False


def test_suggestions_merge_with_off_dedupe_and_keep_store_provenance(monkeypatch):
    service_fixture(monkeypatch, 'name_suggestions', [candidate()])
    monkeypatch.setattr(service.off, 'search_off_candidates_for_item', lambda *a: {
        'provider': 'test', 'results': [dict(candidate(), score=.8), dict(candidate(OTHER), score=.7)]})
    result = service.search_article_candidates({})
    assert len(result['results']) == 2
    assert result['results'][0]['source'] == 'Albert Heijn'
    assert result['results'][0]['evidence_label'] == 'Winkelproduct; suggestie op naam'
    assert result['results'][1]['source'] == 'Open Food Facts'


def test_store_suggestions_survive_off_outage(monkeypatch):
    service_fixture(monkeypatch, 'name_suggestions', [candidate()])
    monkeypatch.setattr(service.off, 'search_off_candidates_for_item', lambda *a: {'provider': 'unavailable', 'results': []})
    result = service.search_article_candidates({})
    assert result['results']
    assert result['provider'] != 'unavailable'
    assert 'OFF is tijdelijk niet bereikbaar' in result['retailer_evidence']['message']


def test_unavailable_store_reuses_existing_off_fallback(monkeypatch):
    service_fixture(monkeypatch, 'unavailable', [])
    monkeypatch.setattr(service.off, 'search_off_candidates_for_item', lambda *a: {'provider': 'test', 'results': [candidate()]})
    result = service.search_article_candidates({})
    assert result['results'][0]['source'] == 'Open Food Facts'
    assert result['retailer_evidence']['status'] == 'unavailable'


def test_conflicting_gtins_are_labelled_suggestions(monkeypatch):
    service_fixture(monkeypatch, 'conflicting_barcodes', [candidate(exact=True), candidate(OTHER, exact=True)])
    monkeypatch.setattr(service.off, 'search_off_candidates_for_item', lambda *a: {'provider': 'test', 'results': []})
    result = service.search_article_candidates({})
    assert all(row['score'] < 1 for row in result['results'])
    assert 'meerdere barcodes' in result['retailer_evidence']['message']


def test_zero_padded_gtin14_can_lookup_same_gtin13_in_off(monkeypatch):
    row = candidate('0' + GTIN, exact=True)
    service_fixture(monkeypatch, 'barcode_found', [row])
    calls = []
    def exact(gtin):
        calls.append(gtin)
        return {'status': 'found', 'product': {'gtin': gtin, 'product_name': 'AH Halfvolle melk'}}
    monkeypatch.setattr(service.off, 'lookup_off_product_by_gtin', exact)
    result = service.search_article_candidates({})
    assert calls == [GTIN]
    assert result['results'][0]['source'] == 'Albert Heijn + Open Food Facts'


def test_store_and_off_candidates_with_gtin13_and_gtin14_dedupe(monkeypatch):
    service_fixture(monkeypatch, 'name_suggestions', [candidate('0' + GTIN)])
    monkeypatch.setattr(service.off, 'search_off_candidates_for_item', lambda *a: {
        'provider': 'test', 'results': [candidate()]})
    assert len(service.search_article_candidates({})['results']) == 1


def test_off_brand_conflict_does_not_overwrite_store_product(monkeypatch):
    service_fixture(monkeypatch, 'barcode_found', [candidate(exact=True)])
    monkeypatch.setattr(service.off, 'lookup_off_product_by_gtin', lambda code: {
        'status': 'found', 'product': {'gtin': code, 'product_name': 'Campina Halfvolle melk', 'brand': 'Campina'}})
    result = service.search_article_candidates({})
    assert result['results'][0]['source'] == 'Albert Heijn'
    assert result['results'][0]['brand'] == 'AH'


@pytest.mark.parametrize('retailer', ['ah', 'Albert Heijn', 'albert-heijn-digitaal'])
def test_digital_ah_retailer_alias_preserves_private_label_guard(retailer):
    source = item()
    source['retailer_code'] = retailer
    assert retail.compatible(source, 'AH Halfvolle melk', 'AH')
    assert not retail.compatible(source, 'Campina Halfvolle melk', 'Campina')
