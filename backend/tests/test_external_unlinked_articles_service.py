import pytest
from sqlalchemy import create_engine, event, text

from app.services import external_unlinked_articles_service as service
from app.services.external_database_route_authorization import required_external_database_permission


@pytest.fixture
def article_engine(monkeypatch):
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        for sql in (
            'CREATE TABLE purchase_import_batches (id TEXT PRIMARY KEY, raw_payload TEXT)',
            '''CREATE TABLE purchase_import_lines (id TEXT PRIMARY KEY, batch_id TEXT,
               external_article_code TEXT, article_name_raw TEXT, brand_raw TEXT,
               quantity_raw TEXT, unit_raw TEXT, created_at TEXT)''',
            'CREATE TABLE receipt_tables (id TEXT PRIMARY KEY, store_name TEXT, created_at TEXT)',
            '''CREATE TABLE receipt_table_lines (id TEXT PRIMARY KEY, receipt_table_id TEXT,
               raw_label TEXT, normalized_label TEXT, barcode TEXT, quantity REAL,
               unit TEXT, line_index INTEGER)''',
        ):
            conn.execute(text(sql))
        conn.execute(text("INSERT INTO purchase_import_batches VALUES ('batch', :payload)"),
                     {'payload': '{"store_name":"Lidl"}'})
    monkeypatch.setattr(service, 'engine', engine)
    yield engine
    engine.dispose()


def insert_articles(engine, names):
    with engine.begin() as conn:
        conn.execute(text('''INSERT INTO purchase_import_lines
            (id, batch_id, external_article_code, article_name_raw, quantity_raw, unit_raw, created_at)
            VALUES (:id, 'batch', :code, :name, '1', 'l', '2026-01-01')'''),
            [{'id': str(i), 'code': code, 'name': name} for i, (name, code) in enumerate(names)])


def test_complete_read_only_overview_deduplicates_context_but_keeps_different_codes(article_engine, monkeypatch):
    names = [(f'Artikel {i}', str(i)) for i in range(550)]
    names += [('Artikel 0', '0'), ('Artikel 0', 'andere-code')]
    insert_articles(article_engine, names)
    with article_engine.begin() as conn:
        conn.execute(text("INSERT INTO receipt_tables VALUES ('receipt', 'Lidl', '2026-01-01')"))
        conn.execute(text("INSERT INTO receipt_table_lines VALUES ('receipt-line', 'receipt', 'Extra artikel', '', NULL, 1, 'stuk', 1)"))
    monkeypatch.setattr(service, 'project_central_link_truth', lambda conn, row: row)

    @event.listens_for(article_engine, 'before_cursor_execute')
    def only_select(conn, cursor, statement, parameters, context, executemany):
        assert statement.strip().upper().startswith('SELECT'), statement

    result = service.list_articles_without_catalog_barcode()
    assert result['total'] == 552
    assert len({row['id'] for row in result['items']}) == 552
    assert any(row['receipt_line_text'] == 'Artikel 549' for row in result['items'])
    assert any(row['receipt_line_text'] == 'Extra artikel' for row in result['items'])
    assert all('household_id' not in row and 'price' not in row for row in result['items'])


def test_only_active_central_link_with_valid_barcode_is_excluded(article_engine, monkeypatch):
    insert_articles(article_engine, [('Exact', ''), ('Generiek', ''), ('Alleen bronbarcode', '8720326035617'), ('Ongeldige barcode', '')])
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
