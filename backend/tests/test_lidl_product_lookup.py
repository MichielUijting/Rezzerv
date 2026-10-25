"""Synthetic protocol and identity boundaries; no live network or database."""
import json
from types import SimpleNamespace

import pytest

from app.services import lidl_product_lookup as lidl
from app.services import external_article_search_service as search
from app.services import off_search_service as off
from app.services.external_database_route_authorization import required_external_database_permission

CODE = '1234567'
GTIN = '8718452504435'
NAME = 'Halfvolle melk'
URL = 'https://www.lidl.nl/p/test/p' + CODE


def page(product=None, extra=None, eans=None):
    product = product or {'@type': 'Product', 'sku': CODE, 'name': NAME, 'brand': {'name': 'Testmerk'}}
    data = '<script type="application/ld+json">' + json.dumps(product) + '</script>'
    if extra:
        data += '<script type="application/ld+json">' + json.dumps(extra) + '</script>'
    if eans is not None:
        # Nuxt reference table: product -> exact ERP and title -> explicit eans.
        table = [{'erpNumber': 1, 'keyfacts': 2, 'eans': 4}, CODE, {'fullTitle': 3}, NAME,
                 list(range(5, 5 + len(eans))), *eans]
        data += '<script id="__NUXT_DATA__" type="application/json">' + json.dumps(table) + '</script>'
    return data


def test_nuxt_explicit_product_ean_and_html_description():
    product = {'@type': 'Product', 'sku': CODE, 'name': NAME, 'description': '<ul><li>1 liter</li></ul>'}
    result = lidl.parse_product_page(page(product, eans=[GTIN]), URL, CODE, NAME)
    assert result['gtins'] == [GTIN]
    assert result['status'] == 'barcode_found'
    assert result['description'] == '1 liter'


def test_never_invent_gtin_or_borrow_from_other_products():
    product = {'@type': 'Product', 'sku': CODE, 'name': NAME,
               'offers': {'gtin13': GTIN}, 'recommendations': [{'gtin13': GTIN}]}
    extra = {'@type': 'Product', 'sku': '9999999', 'name': 'Volle melk', 'gtin13': GTIN}
    result = lidl.parse_product_page(page(product, extra), URL, CODE, NAME)
    assert result['gtins'] == []
    assert result['status'] == 'no_barcode'


@pytest.mark.parametrize('invalid', ['493775', '8718452504436', '0' * 13, '8718452504435junk', '８７１８４５２５０４４３５', 8718452504435])
def test_reject_invalid_or_coerced_codes(invalid):
    assert lidl.parse_product_page(page(eans=[invalid]), URL, CODE, NAME)['gtins'] == []


def test_multiple_valid_barcodes_remain_ambiguous():
    result = lidl.parse_product_page(page(eans=[GTIN, '8720326035617']), URL, CODE, NAME)
    assert result['status'] == 'multiple_barcodes'
    assert len(result['gtins']) == 2


@pytest.mark.parametrize('name', ['Volle melk', 'Magere melk', 'Halfvolle chocolademelk'])
def test_name_or_variant_conflict_rejected(name):
    with pytest.raises(lidl.LidlLookupError, match='name_conflict'):
        lidl.parse_product_page(page(), URL, CODE, name)


@pytest.mark.parametrize('url', ['http://www.lidl.nl/p/x/p1234567', 'https://www.lidl.nl.evil.test/p/x/p1234567',
                                 'https://www.lidl.nl@evil.test/p/x/p1234567', 'https://www.lidl.nl:8443/p/x/p1234567',
                                 'https://www.lidl.nl/account', 'https://www.lidl.nl/p/x/p1234567?next=secret'])
def test_network_boundary(url):
    with pytest.raises(lidl.LidlLookupError):
        lidl.product_url(url)


def test_wrong_product_page_and_duplicate_product_fail_closed():
    with pytest.raises(lidl.LidlLookupError, match='product_mismatch'):
        lidl.parse_product_page(page(), URL + '8', CODE, NAME)
    product = {'@type': 'Product', 'sku': CODE, 'name': NAME}
    with pytest.raises(lidl.LidlLookupError, match='not_found'):
        lidl.parse_product_page(page(product, product), URL, CODE, NAME)


def test_source_code_is_not_used_as_barcode(monkeypatch):
    monkeypatch.setattr(lidl, 'fetch_product_page', lambda code: (page(), URL))
    result = lidl.lookup_lidl_product({'external_article_code': CODE, 'receipt_line_text': NAME})
    assert result['article_number'] == CODE
    assert result['gtins'] == []


def resolved(monkeypatch, retailer='lidl'):
    item = {'receipt_item_id': 'receipt-table-line:synthetic', 'retailer_code': retailer,
            'receipt_line_text': NAME, 'external_article_code': CODE}
    monkeypatch.setattr(off, 'resolve_receipt_item', lambda source_id: dict(item))
    return item


def evidence(status='barcode_found'):
    return {'status': status, 'gtins': [GTIN], 'product_name': NAME, 'brand': 'Testmerk',
            'source_url': URL, 'article_number': CODE}


def test_direct_lidl_gtin_off_enrichment_read_only(monkeypatch):
    resolved(monkeypatch)
    monkeypatch.setattr(search, 'lookup_lidl_product', lambda item: evidence())
    calls = []
    def lookup(gtin):
        calls.append(gtin)
        return {'status': 'found', 'product': {'gtin': gtin, 'product_name': NAME, 'quantity': '1 l'}}
    monkeypatch.setattr(off, 'lookup_off_product_by_gtin', lookup)
    monkeypatch.setattr(off, 'search_off_candidates_for_item', lambda *args: pytest.fail('no fuzzy search for observed GTIN'))
    result = search.search_article_candidates({'receipt_item_id': 'receipt-table-line:synthetic',
        'external_article_code': 'evil', 'retailer_code': 'evil', 'source_url': 'https://evil.test'})
    assert calls == [GTIN]
    assert result['results'][0]['quantity'] == '1 l'
    assert result['results'][0]['source'] == 'Lidl + Open Food Facts'
    for key in ('mutated', 'creates_global_product', 'creates_household_article', 'creates_inventory_event', 'creates_external_candidate'):
        assert result[key] is False


@pytest.mark.parametrize('off_result', [{'status': 'external_source_unavailable'}, {'status': 'not_found'},
    {'status': 'found', 'product': {'gtin': GTIN, 'product_name': 'Volle melk'}}])
def test_off_failure_or_conflict_preserves_only_store_evidence(monkeypatch, off_result):
    resolved(monkeypatch)
    monkeypatch.setattr(search, 'lookup_lidl_product', lambda item: evidence())
    monkeypatch.setattr(off, 'lookup_off_product_by_gtin', lambda code: off_result)
    result = search.search_article_candidates({})
    assert result['results'][0]['product_name'] == NAME
    assert result['results'][0]['source'] == 'Lidl Nederland'


@pytest.mark.parametrize('status', ['unavailable', 'not_found', 'no_article_number', 'no_barcode', 'multiple_barcodes'])
def test_fallback_reuses_off_and_retains_evidence(monkeypatch, status):
    item = resolved(monkeypatch)
    monkeypatch.setattr(search, 'lookup_lidl_product', lambda item: evidence(status))
    calls = []
    def fallback(payload, resolved_item):
        calls.append((payload, resolved_item))
        return {'provider': 'unavailable' if status == 'unavailable' else 'test',
                'results': [{'gtin': GTIN, 'product_name': NAME, 'score': .8}], 'mutated': False}
    monkeypatch.setattr(off, 'search_off_candidates_for_item', fallback)
    result = search.search_article_candidates({})
    assert len(calls) == 1
    assert calls[0][1]['receipt_item_id'] == item['receipt_item_id']
    assert result['retailer_evidence']['status'] == status
    assert result['results'][0]['evidence_label'] == 'Suggestie op artikelnaam'


def test_other_retailer_never_calls_lidl(monkeypatch):
    resolved(monkeypatch, 'Jumbo')
    monkeypatch.setattr(search, 'lookup_lidl_product', lambda item: pytest.fail('wrong retailer'))
    monkeypatch.setattr(off, 'search_off_candidates_for_item', lambda *args: {'results': [], 'provider': 'test'})
    assert search.search_article_candidates({})['retailer_evidence'] is None


def test_search_permission_and_feature_flag_authority():
    assert required_external_database_permission('POST', '/api/external-databases/products/search-preview') == 'platform.external_products.search'


def test_transport_blocks_cross_host_redirect_before_get(monkeypatch):
    calls = []
    def open_request(request, **kwargs):
        calls.append(request.full_url)
        raise lidl.urllib.error.HTTPError(request.full_url, 302, 'redirect', {'Location': 'https://evil.test/p/x/p' + CODE}, None)
    monkeypatch.setattr(lidl.urllib.request, 'build_opener', lambda *args: SimpleNamespace(open=open_request))
    with pytest.raises(lidl.LidlLookupError):
        lidl.fetch_product_page(CODE)
    assert calls == ['https://www.lidl.nl/p/-/p' + CODE]


def test_nuxt_brand_prefixed_full_title_uses_exact_plain_title():
    table = [{'erpNumber': 1, 'keyfacts': 2, 'eans': 5}, CODE,
             {'fullTitle': 3, 'title': 4}, 'Testmerk ' + NAME, NAME, [6], GTIN]
    data = page() + '<script id="__NUXT_DATA__">' + json.dumps(table) + '</script>'
    assert lidl.parse_product_page(data, URL, CODE, NAME)['gtins'] == [GTIN]


def test_nuxt_other_product_code_cannot_supply_ean():
    table = [{'erpNumber': 1, 'keyfacts': 2, 'eans': 4}, '9999999', {'title': 3}, NAME, [5], GTIN]
    data = page() + '<script id="__NUXT_DATA__">' + json.dumps(table) + '</script>'
    assert lidl.parse_product_page(data, URL, CODE, NAME)['gtins'] == []


def test_source_resolvers_preserve_separate_article_code(monkeypatch):
    calls = []
    row = {'receipt_line_text': NAME, 'external_article_code': CODE, 'retailer_code': 'Lidl',
           'quantity': '1', 'unit': 'l', 'batch_raw_payload': '{"retailer":"Lidl"}'}
    def execute(statement, args):
        calls.append(str(statement))
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row))
    monkeypatch.setattr(off, '_table_exists', lambda *args: True)
    conn = SimpleNamespace(execute=execute)
    for resolver in (off._resolve_receipt_table_line, off._resolve_purchase_import_line):
        result = resolver(conn, 'synthetic')
        assert result['external_article_code'] == CODE
        assert result['receipt_line_text'] == NAME
    assert all('external_article_code' in sql for sql in calls)


def test_retains_feature_flag_and_denies_missing_authority(monkeypatch):
    from fastapi import HTTPException
    from app.services import external_database_route_authorization as auth
    monkeypatch.setattr(auth, 'evaluate_platform_permission', lambda *args, **kwargs: SimpleNamespace(allowed=False))
    with pytest.raises(HTTPException) as denied:
        auth.authorize_external_database_request(None, user_id='test', method='POST', path='/api/external-databases/products/search-preview')
    assert denied.value.status_code == 403
    monkeypatch.setattr(auth, 'evaluate_platform_permission', lambda *args, **kwargs: SimpleNamespace(allowed=True))
    monkeypatch.setattr(auth, 'is_platform_feature_enabled', lambda *args: False)
    with pytest.raises(HTTPException) as disabled:
        auth.authorize_external_database_request(None, user_id='test', method='POST', path='/api/external-databases/products/search-preview')
    assert disabled.value.status_code == 503
