from contextlib import nullcontext
from types import SimpleNamespace

from app.services import external_unlinked_articles_service as service
from app.services.external_database_route_authorization import required_external_database_permission


def article_sources(monkeypatch, names, receipts=()):
    """Unit-test connection double; database execution belongs to PostgreSQL CI."""
    purchases = [dict(purchase_import_line_id=str(i), external_article_code=code,
                      article_name_raw=name, quantity_raw='1', unit_raw='l',
                      batch_raw_payload='{"store_name":"Lidl"}')
                 for i, (name, code) in enumerate(names)]
    statements = []

    def execute(statement):
        sql = str(statement).strip()
        assert sql.upper().startswith('SELECT'), sql
        statements.append(sql)
        rows = purchases if 'FROM purchase_import_lines' in sql else list(receipts)
        return SimpleNamespace(mappings=lambda: iter(rows))

    conn = SimpleNamespace(execute=execute)
    monkeypatch.setattr(service, 'engine', SimpleNamespace(connect=lambda: nullcontext(conn)))
    return statements


def test_complete_read_only_overview_deduplicates_context_but_keeps_different_codes(monkeypatch):
    names = [(f'Artikel {i}', str(i)) for i in range(550)]
    names += [('Artikel 0', '0'), ('Artikel 0', 'andere-code')]
    statements = article_sources(monkeypatch, names, [dict(receipt_line_id='receipt-line',
        retailer_code='Lidl', receipt_line_text='Extra artikel', retailer_article_number=None,
        quantity_label='1 stuk')])
    monkeypatch.setattr(service, 'project_central_link_truth', lambda conn, row: row)

    result = service.list_articles_without_catalog_barcode()
    assert len(statements) == 2
    assert result['total'] == 552
    assert len({row['id'] for row in result['items']}) == 552
    assert any(row['receipt_line_text'] == 'Artikel 549' for row in result['items'])
    assert any(row['receipt_line_text'] == 'Extra artikel' for row in result['items'])
    assert all('household_id' not in row and 'price' not in row for row in result['items'])


def test_only_active_central_link_with_valid_barcode_is_excluded(monkeypatch):
    article_sources(monkeypatch, [('Exact', ''), ('Generiek', ''), ('Alleen bronbarcode', '8720326035617'), ('Ongeldige barcode', '')])
    states = {
        'Exact': (True, '8720326035617'),
        'Generiek': (True, ''),
        'Alleen bronbarcode': (False, ''),
        'Ongeldige barcode': (True, '8720326035618'),
    }

    def project(conn, row):
        active, gtin = states[row['receipt_line_text']]
        return {**row, 'central_link_active': active, 'linked_gtin': gtin}

    monkeypatch.setattr(service, 'project_central_link_truth', project)
    result = service.list_articles_without_catalog_barcode()
    assert {item['receipt_line_text'] for item in result['items']} == {
        'Generiek', 'Alleen bronbarcode', 'Ongeldige barcode',
    }


def test_new_overview_requires_existing_platform_read_permission():
    assert required_external_database_permission('GET', '/api/external-databases/unlinked-articles') == 'platform.external_products.view'
