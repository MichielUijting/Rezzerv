from contextlib import nullcontext
from types import SimpleNamespace

from app.services import external_unlinked_articles_service as service
from app.services.external_database_route_authorization import required_external_database_permission


def article_sources(monkeypatch, names, receipts=(), manual_rows=()):
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
        rows = (list(manual_rows) if 'FROM ed2_manual_barcodes' in sql else
                purchases if 'FROM purchase_import_lines' in sql else list(receipts))
        return SimpleNamespace(mappings=lambda: iter(rows))

    conn = SimpleNamespace(execute=execute)
    monkeypatch.setattr(service, 'engine', SimpleNamespace(connect=lambda: nullcontext(conn)))
    monkeypatch.setattr(service, 'inspect', lambda connection: SimpleNamespace(
        has_table=lambda name: name == "ed2_manual_barcodes" and bool(manual_rows)))
    monkeypatch.setattr(service, 'get_pending_classification_external_article_link', lambda *a, **kw: None)
    return statements


def test_complete_read_only_overview_deduplicates_exact_text_and_chain_regardless_of_code(monkeypatch):
    names = [(f'Artikel {i}', str(i)) for i in range(550)]
    names += [('Artikel 0', '0'), ('Artikel 0', 'andere-code')]
    statements = article_sources(monkeypatch, names, [dict(receipt_line_id='receipt-line',
        retailer_code='Lidl', receipt_line_text='Extra artikel', retailer_article_number=None,
        quantity_label='1 stuk')])
    monkeypatch.setattr(service, 'project_central_link_truth', lambda conn, row: row)

    result = service.list_articles_without_catalog_barcode()
    assert len(statements) == 2
    assert result['total'] == 551
    assert len({row['id'] for row in result['items']}) == 551
    assert any(row['receipt_line_text'] == 'Artikel 549' for row in result['items'])
    assert any(row['receipt_line_text'] == 'Extra artikel' for row in result['items'])
    assert all('household_id' not in row and 'price' not in row for row in result['items'])


def test_exact_spelling_and_chain_define_duplicates_not_casefold_or_fuzzy_names(monkeypatch):
    article_sources(monkeypatch, [('Melk', '1'), ('Melk', '2'), ('melk', '3'),
                                 ('Volle melk', '4'), ('Volle  melk', '5'), ('Pate', '6'), ('Paté', '7')],
        [dict(receipt_line_id='ah', retailer_code='Albert Heijn', receipt_line_text='Melk', retailer_article_number='8'),
         dict(receipt_line_id='ah-alias', retailer_code='ah', receipt_line_text='Melk', retailer_article_number='9')])
    monkeypatch.setattr(service, 'project_central_link_truth', lambda conn, row: row)
    result = service.list_articles_without_catalog_barcode()
    assert result['total'] == 7
    assert sum(row['receipt_line_text'] == 'Melk' for row in result['items']) == 2
    assert {row['retailer_code'] for row in result['items']} == {'lidl', 'ah'}


def test_linked_first_code_does_not_hide_unlinked_code_with_same_display_name(monkeypatch):
    article_sources(monkeypatch, [('Melk', 'linked'), ('Melk', 'unlinked')])
    monkeypatch.setattr(service, 'project_central_link_truth', lambda conn, row: {
        **row, 'central_link_active': row['external_article_code'] == 'linked', 'linked_gtin': '8720326035617'})
    result = service.list_articles_without_catalog_barcode()
    assert result['total'] == 1
    assert result['items'][0]['receipt_article_number'] == 'unlinked'


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


def test_verified_catalog_gtin_waiting_for_gpc_is_not_an_unlinked_barcode(monkeypatch):
    article_sources(monkeypatch, [('Achterham BL', '6604471'), ('Onbekend', '42')])
    monkeypatch.setattr(service, 'project_central_link_truth', lambda conn, row: row)
    pending_calls = []

    def pending(conn, **identity):
        pending_calls.append(identity)
        return {'status': 'classification_pending', 'global_product_id': 'catalog-1'} \
            if identity['receipt_text'] == 'Achterham BL' else None

    monkeypatch.setattr(service, 'get_pending_classification_external_article_link', pending)
    result = service.list_articles_without_catalog_barcode()
    assert [item['receipt_line_text'] for item in result['items']] == ['Onbekend']
    assert pending_calls[0]['retailer_code'].lower() == 'lidl'
    assert pending_calls[0]['external_article_code'] == '6604471'


def test_new_overview_requires_existing_platform_read_permission():
    assert required_external_database_permission('GET', '/api/external-databases/unlinked-articles') == 'platform.external_products.view'


def test_all_articles_overview_includes_linked_unlinked_pending_and_generic(monkeypatch):
    article_sources(monkeypatch, [
        ('Melk', 'linked'), ('Melk', 'missing'), ('Kaas', 'pending'),
        ('Bouillon', 'generic'), ('Leeg artikel', 'none'), ('Leeg artikel', 'none'),
    ])

    def project(conn, row):
        code = row['external_article_code']
        return {
            **row, 'central_link_active': code in {'linked', 'generic'},
            'linked_gtin': '8720326035617' if code == 'linked' else '',
            'is_generic_catalog_link': code == 'generic',
        }

    monkeypatch.setattr(service, 'project_central_link_truth', project)
    monkeypatch.setattr(service, 'get_pending_classification_external_article_link',
        lambda conn, **identity: {'primary_gtin': '8718452504435'}
        if identity['external_article_code'] == 'pending' else None)
    payload = service.list_all_external_articles()
    assert payload['total'] == 5
    assert payload['counts'] == {'unlinked': 2, 'classification_pending': 1, 'linked': 2}
    by_code = {item['receipt_article_number']: item for item in payload['items']}
    assert by_code['linked']['article_code'] == '8720326035617'
    assert by_code['missing']['article_code'] == ''
    assert by_code['pending']['article_code'] == '8718452504435'
    assert by_code['pending']['link_status'] == 'classification_pending'
    assert by_code['generic']['link_status'] == 'linked'
    assert by_code['generic']['is_generic_catalog_link'] is True
    assert by_code['generic']['article_code'] == ''
    assert not any('household_id' in item for item in payload['items'])


def test_all_articles_overview_does_not_infer_catalog_code_from_receipt_article_number(monkeypatch):
    article_sources(monkeypatch, [('Melk', '8720326035617')])
    monkeypatch.setattr(service, 'project_central_link_truth', lambda conn, row: row)
    result = service.list_all_external_articles()
    assert result['total'] == 1
    assert result['items'][0]['article_code'] == ''
    assert result['counts']['unlinked'] == 1


def test_all_articles_overview_requires_platform_view_permission():
    assert required_external_database_permission(
        'GET', '/api/external-databases/articles-overview'
    ) == 'platform.external_products.view'


def test_overview_exposes_unlink_identity_only_for_confirmed_off_links(monkeypatch):
    article_sources(monkeypatch, [('OFF gekoppeld', 'a'), ('OFF wacht', 'b'),
                                 ('Generiek', 'c'), ('GTIN fallback', 'd')])

    def projection(conn, source):
        code = source['external_article_code']
        return {**source,
                'central_link_active': code in {'a', 'c', 'd'},
                'central_external_article_product_link': {
                    'id': f'link-{code}',
                    'confirmed_by': 'external_databases_off_manual_link' if code == 'a'
                    else 'external_databases_generic_link' if code == 'c' else '',
                },
                'linked_gtin': '8720326035617'}

    monkeypatch.setattr(service, 'project_central_link_truth', projection)
    monkeypatch.setattr(service, 'get_pending_classification_external_article_link',
                        lambda conn, **identity: {
                            'id': 'link-b', 'confirmed_by': 'external_databases_off_pending_gpc',
                            'global_product_id': 'catalog-b',
                            'primary_gtin': '8718452504435',
                        } if identity['external_article_code'] == 'b' else None)
    rows = {row['receipt_article_number']: row
            for row in service.list_all_external_articles()['items']}
    assert rows['a']['off_link_id'] == 'link-a'
    assert rows['b']['off_link_id'] == 'link-b'
    assert rows['b']['pending_global_product_id'] == 'catalog-b'
    assert all(rows[code]['pending_global_product_id'] == '' for code in ('a', 'c', 'd'))
    assert rows['c']['off_link_id'] == ''
    assert rows['d']['off_link_id'] == ''



def test_saved_albert_heijn_barcode_is_projected_after_reload_as_ah(monkeypatch):
    """The exact reported SIMON LEVELT case: no browser-side retailer alias mismatch."""
    code = '8711138357776'
    article_sources(monkeypatch, [], receipts=[
        dict(receipt_line_id='simon-receipt-id', retailer_code='Albert Heijn',
             receipt_line_text='SIMON LEVELT', retailer_article_number='768682',
             quantity_label='1 stuk'),
    ], manual_rows=[
        dict(retailer_code='albert-heijn', receipt_text_normalized='simon levelt',
             external_article_code='768682', gtin=code),
    ])
    monkeypatch.setattr(service, 'project_central_link_truth', lambda conn, source: source)
    overview = service.list_all_external_articles()
    row = overview['items'][0]
    assert row['id'] == 'receipt-table-line:simon-receipt-id'
    assert row['retailer_code'] == 'ah'
    assert row['article_code'] == ''
    assert row['manual_barcode'] == code
    assert row['link_status'] == 'unlinked'
    assert overview['counts']['unlinked'] == 1


def test_manual_barcode_is_not_cross_linked_between_receipt_codes(monkeypatch):
    code = '8711138357776'
    article_sources(monkeypatch, [], receipts=[
        dict(receipt_line_id='simon-one', retailer_code='Albert Heijn',
             receipt_line_text='SIMON LEVELT', retailer_article_number='768682',
             quantity_label='1 stuk'),
        dict(receipt_line_id='simon-other', retailer_code='Albert Heijn',
             receipt_line_text='SIMON LEVELT', retailer_article_number='different-code',
             quantity_label='1 stuk'),
    ], manual_rows=[
        dict(retailer_code='albert-heijn', receipt_text_normalized='simon levelt',
             external_article_code='768682', gtin=code),
    ])
    monkeypatch.setattr(service, 'project_central_link_truth', lambda conn, source: source)
    overview = service.list_all_external_articles()
    by_article = {row['receipt_article_number']: row for row in overview['items']}
    assert by_article['768682']['manual_barcode'] == code
    assert by_article['different-code']['manual_barcode'] == ''
    assert all(row['link_status'] == 'unlinked' for row in overview['items'])


def test_unlinked_rows_with_no_possible_link_do_not_trigger_n_plus_one_queries(monkeypatch):
    """Most imported receipt rows are unlinked; expensive projection is needless."""
    article_sources(monkeypatch, [('Onbekend', 'winkelcode-42'), ('Melk', '123')])
    monkeypatch.setattr(service, '_central_link_keys', lambda conn: (
        {('lidl', '123')}, set(),
    ))
    resolved = []
    def project(conn, source):
        resolved.append(source['receipt_line_text'])
        return {**source, 'central_link_active': True, 'linked_gtin': ''}
    monkeypatch.setattr(service, 'project_central_link_truth', project)
    pending = []
    monkeypatch.setattr(service, 'get_pending_classification_external_article_link',
                        lambda conn, **kw: pending.append(kw) or None)
    result = service.list_all_external_articles()
    assert result['total'] == 2
    assert resolved == ['Melk']
    assert len(pending) == 0
    assert result['counts'] == {'unlinked': 1, 'classification_pending': 0, 'linked': 1}


def test_read_optimisation_keeps_text_links_ah_aliases_and_gtin_fallbacks():
    keys = ({('ah', '123')}, {('lidl', 'melk 1 l')})
    assert service._requires_central_resolution({
        'retailer_code': 'Albert Heijn', 'external_article_code': '123',
        'receipt_line_text': 'Ander product',
    }, keys)
    assert service._requires_central_resolution({
        'retailer_code': 'Lidl', 'external_article_code': '',
        'receipt_line_text': 'Mélk  1 L',
    }, keys)
    assert service._requires_central_resolution({
        'retailer_code': 'Jumbo', 'external_article_code': '765',
        'receipt_line_text': 'GTIN zonder centrale koppeling',
        'gtin': '8711138357776',
    }, keys)
    assert service._requires_central_resolution({
        'retailer_code': 'Jumbo', 'external_article_code': '765',
        'receipt_line_text': 'Kandidaat met GTIN',
        'candidates': [{'barcode': '8711138357776'}],
    }, keys)
    assert not service._requires_central_resolution({
        'retailer_code': 'Jumbo', 'external_article_code': '765',
        'receipt_line_text': 'Geen match',
    }, keys)
    assert service._requires_central_resolution({'receipt_line_text': 'Legacy'}, None)


def test_central_link_prefetch_reads_only_active_identifiers(monkeypatch):
    seen = []
    class Result:
        def mappings(self):
            return iter([
                {'retailer_code': 'albert-heijn', 'external_article_code': ' 123 ',
                 'receipt_text_normalized': 'Mélk  1 L'},
                {'retailer_code': 'jumbo', 'external_article_code': '',
                 'receipt_text_normalized': 'cacao'},
            ])
    class FakeConnection:
        def execute(self, query):
            seen.append(str(query))
            return Result()
    monkeypatch.setattr(service, 'inspect', lambda conn: type('Inspect', (), {
        'has_table': lambda self, name: name == 'external_article_product_links',
    })())
    result = service._central_link_keys(FakeConnection())
    assert result == ({('ah', '123')}, {('ah', 'melk 1 l'), ('jumbo', 'cacao')})
    assert len(seen) == 1
    assert "status IN ('confirmed', 'classification_pending')" in seen[0]
