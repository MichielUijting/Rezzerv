"""ED2 GPC completion must revalidate staged identity and commit atomically."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.services import external_off_gpc_assignment_service as service
from app.services.external_database_route_authorization import required_external_database_permission


ARTICLE = 'receipt-table-line:achterham'
LINK = 'off-pending-achterham'
PRODUCT = 'catalog-achterham'
BRICK = '10000001'


def fake_pending_database(monkeypatch, *, current_status='classification_pending',
                          locked_link=True, official_after_write=True):
    state = {'status': current_status, 'membership': False, 'gpc': False, 'persisted': False}
    executed_sql = []
    writers = []

    class Result:
        def __init__(self, row):
            self.row = row

        def mappings(self):
            return self

        def first(self):
            return self.row

    class Connection:
        def execute(self, statement, params):
            sql = str(statement)
            executed_sql.append(sql)
            assert sql.lstrip().upper().startswith('SELECT'), sql
            if 'FOR UPDATE OF link, gp' in sql:
                return Result({'id': LINK, 'global_product_id': PRODUCT,
                               'confirmed_by': 'external_databases_off_pending_gpc',
                               'name': 'Achterham BL', 'brand': 'Zwagerman',
                               'primary_gtin': '8718452504435', 'product_status': 'active'}
                              if locked_link else None)
            if 'FROM global_product_gpc_bricks' in sql:
                return Result(None)
            raise AssertionError(f'Unexpected query: {sql}')

    @contextmanager
    def begin():
        snapshot = dict(state)
        try:
            yield Connection()
        except Exception:
            state.clear()
            state.update(snapshot)
            raise

    def overview(*, conn=None):
        assert conn is not None
        status = 'linked' if state['membership'] and state['gpc'] and official_after_write else state['status']
        return {'items': [{'id': ARTICLE, 'link_status': status, 'off_link_id': LINK,
                           'pending_global_product_id': PRODUCT,
                           'retailer_code': 'lidl', 'receipt_line_text': 'Achterham BL'}]}

    def complete(conn, product_id):
        assert product_id == PRODUCT
        return {'is_generic_catalog_product': False, 'has_valid_primary_gtin': True,
                'has_matching_gtin_identity': True, 'has_active_official_gpc': state['membership']}

    def ensure_type(conn, code):
        assert code == BRICK
        writers.append('ensure-official')
        return 'gpc:' + code

    def create_membership(conn, **kwargs):
        assert kwargs == {
            'global_product_id': PRODUCT, 'inventory_group_key': 'gpc:' + BRICK,
            'comparison_group_key': 'gpc:' + BRICK, 'confidence': 1.0,
            'source': 'manual_gs1_gpc', 'confirmed_by_user': True,
        }
        writers.append('membership')
        state['membership'] = True
        return {'ok': True}

    def assign_gpc(conn, **kwargs):
        assert kwargs == {'global_product_id': PRODUCT, 'brick_code': BRICK,
                          'gpc_source': 'manual', 'confidence': 1.0}
        writers.append('assignment')
        state['gpc'] = True

    def persist(conn, product_id, product, code):
        assert product_id == PRODUCT and code == BRICK
        writers.append('product-type')
        state['persisted'] = True

    monkeypatch.setattr(service, 'engine', SimpleNamespace(begin=begin))
    monkeypatch.setattr(service, 'list_all_external_articles', overview)
    monkeypatch.setattr(service, '_complete_global_product_link_data', complete)
    monkeypatch.setattr(service, '_ensure_official_gpc_product_type', ensure_type)
    monkeypatch.setattr(service, 'link_global_product_to_inventory_group_with_connection', create_membership)
    monkeypatch.setattr(service, '_persist_global_product_gpc_assignment', assign_gpc)
    monkeypatch.setattr(service, 'persist_product_type', persist)
    monkeypatch.setattr(service, 'assert_external_product_identity_compatible', lambda **kw: None)
    monkeypatch.setattr(service, 'gpc_brick_conflict', lambda product, code: '')
    return state, writers, executed_sql


def test_pending_off_gpc_completes_canonical_type_and_ed2_link_in_one_transaction(monkeypatch):
    state, writers, queries = fake_pending_database(monkeypatch)
    result = service.classify_pending_off_article(receipt_item_id=ARTICLE, link_id=LINK, brick_code=BRICK)
    assert result == {'ok': True, 'linked': True, 'receipt_item_id': ARTICLE,
                      'global_product_id': PRODUCT, 'gpc_brick_code': BRICK,
                      'mutates_receipt_or_inventory': False}
    assert state['membership'] and state['gpc'] and state['persisted']
    assert writers == ['ensure-official', 'membership', 'assignment', 'product-type']
    assert all('purchase_import_lines' not in query and 'household_articles' not in query
               and 'UPDATE' not in query.upper() for query in queries)


@pytest.mark.parametrize('receipt_id,link_id,code', [
    ('', LINK, BRICK), (ARTICLE, '', BRICK), (ARTICLE, LINK, '100'),
    (ARTICLE, LINK, 'abcd1234'),
])
def test_bad_input_rejected_before_database_write(monkeypatch, receipt_id, link_id, code):
    state, writers, queries = fake_pending_database(monkeypatch)
    with pytest.raises(ValueError):
        service.classify_pending_off_article(receipt_item_id=receipt_id, link_id=link_id, brick_code=code)
    assert not writers and not queries and not state['gpc']


def test_stale_or_tampered_pending_link_rejected_without_writes(monkeypatch):
    for status, locked in [('linked', True), ('classification_pending', False)]:
        state, writers, queries = fake_pending_database(monkeypatch, current_status=status, locked_link=locked)
        with pytest.raises(ValueError, match='wijzigd|beschikbaar'):
            service.classify_pending_off_article(receipt_item_id=ARTICLE, link_id=LINK, brick_code=BRICK)
        assert not state['gpc'] and not writers


def test_incomplete_link_after_assignment_rolls_back(monkeypatch):
    state, writers, _ = fake_pending_database(monkeypatch, official_after_write=False)
    with pytest.raises(ValueError, match='teruggedraaid'):
        service.classify_pending_off_article(receipt_item_id=ARTICLE, link_id=LINK, brick_code=BRICK)
    assert writers == ['ensure-official', 'membership', 'assignment', 'product-type']
    assert state['membership'] is False and state['gpc'] is False and state['persisted'] is False


def test_unknown_gpc_brick_rejected_and_rolled_back(monkeypatch):
    state, writers, _ = fake_pending_database(monkeypatch)

    def reject(conn, code):
        raise ValueError('Onbekende GS1 GPC Brickcode')

    monkeypatch.setattr(service, '_ensure_official_gpc_product_type', reject)
    with pytest.raises(ValueError, match='Onbekende GS1'):
        service.classify_pending_off_article(receipt_item_id=ARTICLE, link_id=LINK, brick_code=BRICK)
    assert not writers and not state['gpc'] and not state['membership']


def test_off_identity_or_gpc_compatibility_conflict_is_not_silently_overridden(monkeypatch):
    for source, attribute, replacement in (
        ('Merkidentiteit past niet', 'assert_external_product_identity_compatible',
         lambda **kw: (_ for _ in ()).throw(ValueError('Merkidentiteit past niet'))),
        ('Productomschrijving conflicteert', 'gpc_brick_conflict',
         lambda product, code: 'Productomschrijving conflicteert'),
    ):
        state, writers, _ = fake_pending_database(monkeypatch)
        monkeypatch.setattr(service, attribute, replacement)
        with pytest.raises(ValueError, match=source):
            service.classify_pending_off_article(receipt_item_id=ARTICLE, link_id=LINK, brick_code=BRICK)
        assert not writers and not state['gpc'] and not state['membership']


def test_dedicated_write_endpoint_requires_platform_link_authority():
    assert required_external_database_permission(
        'POST', '/api/external-databases/off/classify-pending',
    ) == 'platform.external_products.link_existing'
