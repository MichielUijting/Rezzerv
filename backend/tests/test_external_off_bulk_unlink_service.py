"""ED2 bulk unlink may only deactivate explicitly selected central OFF relations."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.services import external_off_bulk_unlink_service as service
from app.services.external_database_route_authorization import required_external_database_permission


def row(article_id, link_id, *, status='linked'):
    return {
        'id': article_id, 'off_link_id': link_id,
        'link_status': status,
    }


def fake_database(monkeypatch, source_rows):
    stored = {value['off_link_id']: 'confirmed' for value in source_rows if value['off_link_id']}
    executed_sql = []

    class Connection:
        def execute(self, statement, params):
            sql = str(statement)
            executed_sql.append(sql)
            assert sql.lstrip().upper().startswith('UPDATE EXTERNAL_ARTICLE_PRODUCT_LINKS')
            link_id = params['link_id']
            if stored.get(link_id) != 'confirmed':
                return SimpleNamespace(rowcount=0)
            stored[link_id] = 'inactive'
            return SimpleNamespace(rowcount=1)

    @contextmanager
    def begin():
        before = dict(stored)
        try:
            yield Connection()
        except Exception:
            stored.clear()
            stored.update(before)
            raise

    def overview(*, conn=None):
        assert conn is not None
        items = [dict(source, off_link_id=source['off_link_id'] if stored.get(source['off_link_id']) == 'confirmed' else '',
                      link_status=source['link_status'] if stored.get(source['off_link_id']) == 'confirmed' else 'unlinked')
                 for source in source_rows]
        return {'items': items}

    monkeypatch.setattr(service, 'engine', SimpleNamespace(begin=begin))
    monkeypatch.setattr(service, 'list_all_external_articles', overview)
    return stored, executed_sql


def test_bulk_unlink_changes_only_selected_off_link_records(monkeypatch):
    stored, sql = fake_database(monkeypatch, [row('receipt-table-line:1', 'off-a'), row('receipt-table-line:2', 'off-b')])
    result = service.unlink_selected_off_article_links([
        {'receipt_item_id': 'receipt-table-line:1', 'link_id': 'off-a'},
        {'receipt_item_id': 'receipt-table-line:2', 'link_id': 'off-b'},
    ])
    assert result['ok'] is True
    assert result['unlinked_articles'] == 2
    assert result['unlinked_links'] == 2
    assert result['mutates_receipt_or_inventory'] is False
    assert stored == {'off-a': 'inactive', 'off-b': 'inactive'}
    assert len(sql) == 2
    assert all('purchase_import_lines' not in query and 'household_articles' not in query
               and 'inventory' not in query for query in sql)
    assert all("confirmed_by = 'external_databases_off_unlinked'" in query for query in sql)


def test_bulk_unlink_rejects_incompatible_and_stale_selections_without_writes(monkeypatch):
    stored, sql = fake_database(monkeypatch, [row('receipt-table-line:1', 'off-a'), row('receipt-table-line:2', '')])
    for selections in (
        [],
        [{'receipt_item_id': 'receipt-table-line:1', 'link_id': 'wrong'}],
        [{'receipt_item_id': 'receipt-table-line:2', 'link_id': 'unknown'}],
        [{'receipt_item_id': 'receipt-table-line:1', 'link_id': 'off-a'}] * 2,
        [{'receipt_item_id': 'receipt-table-line:missing', 'link_id': 'off-a'}],
    ):
        with pytest.raises(ValueError):
            service.unlink_selected_off_article_links(selections)
    assert stored == {'off-a': 'confirmed'}
    assert sql == []


def test_shared_off_link_must_be_completely_selected(monkeypatch):
    stored, sql = fake_database(monkeypatch, [row('receipt-table-line:1', 'off-a'), row('receipt-table-line:2', 'off-a')])
    with pytest.raises(ValueError, match='meer bonartikelen'):
        service.unlink_selected_off_article_links([{'receipt_item_id': 'receipt-table-line:1', 'link_id': 'off-a'}])
    assert stored == {'off-a': 'confirmed'}
    assert sql == []


def test_bulk_unlink_rolls_back_entire_batch_on_stale_link(monkeypatch):
    stored, sql = fake_database(monkeypatch, [row('receipt-table-line:1', 'off-a'), row('receipt-table-line:2', 'off-b')])
    original_overview = service.list_all_external_articles

    def conflicting_overview(*, conn=None):
        result = original_overview(conn=conn)
        # Return the preflight snapshot, then simulate a second actor changing
        # off-b just before SQL updates it.
        if not sql:
            stored['off-b'] = 'inactive'
        return result

    monkeypatch.setattr(service, 'list_all_external_articles', conflicting_overview)
    with pytest.raises(ValueError, match='tussentijds gewijzigd'):
        service.unlink_selected_off_article_links([
            {'receipt_item_id': 'receipt-table-line:1', 'link_id': 'off-a'},
            {'receipt_item_id': 'receipt-table-line:2', 'link_id': 'off-b'},
        ])
    assert stored == {'off-a': 'confirmed', 'off-b': 'confirmed'}


def test_new_write_route_requires_existing_platform_link_permission():
    assert required_external_database_permission(
        'POST', '/api/external-databases/off/unlink-selected'
    ) == 'platform.external_products.link_existing'
