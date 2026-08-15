from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics


def test_unknown_physical_article_is_inventory_product():
    result = derive_receipt_line_semantics({'raw_label': 'Onbekend fysiek artikel'})
    assert result == {'line_role': 'product', 'inventory_eligible': True}


def test_split_loyalty_line_uses_semantic_label_not_detail_text():
    result = derive_receipt_line_semantics({
        'raw_label': '51 x 0,10 5,10',
        'normalized_label': 'Koopzegel Digital',
        'quantity': 51,
        'unit_price': 0.10,
        'line_total': 5.10,
    })
    assert result == {'line_role': 'loyalty', 'inventory_eligible': False}


def test_producer_trace_loyalty_is_authoritative_even_when_text_has_no_keyword():
    result = derive_receipt_line_semantics({
        'raw_label': '51 x 0,10 5,10',
        'producer_trace': {
            'line_type': 'spaarzegels',
            'is_spaarzegels': True,
            'exclude_from_inventory': True,
            'external_matching_allowed': False,
        },
    })
    assert result == {'line_role': 'loyalty', 'inventory_eligible': False}


def test_generic_discount_wording_is_financial_not_inventory():
    for label in ('In prijs verlaagd', 'Prijsverlaging', 'Afgeprijsd', 'Reduced price'):
        result = derive_receipt_line_semantics({'normalized_label': label, 'line_total': -0.20})
        assert result['line_role'] == 'financial', label
        assert result['inventory_eligible'] is False, label


def test_generic_non_inventory_charges_are_financial():
    for label in ('Statiegeld 0,25', 'Emballage 0,50', 'Verzendkosten 4,95', 'Delivery fee 3,50'):
        result = derive_receipt_line_semantics({'normalized_label': label})
        assert result['inventory_eligible'] is False, label


def test_persisted_semantics_are_not_reclassified_downstream():
    result = derive_receipt_line_semantics({
        'raw_label': 'arbitrary display text',
        'line_role': 'loyalty',
        'inventory_eligible': 0,
    })
    assert result == {'line_role': 'loyalty', 'inventory_eligible': False}


def test_semantic_columns_live_in_central_receipt_schema_evolution():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / 'app/main.py').read_text(encoding='utf-8')
    start = source.index('line_additions = {')
    block = source[start:start + 1200]
    assert "'line_role': 'TEXT'" in block
    assert "'inventory_eligible': 'INTEGER'" in block


def test_receipt_service_persists_semantics_on_both_ingest_paths():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / 'app/services/receipt_service.py').read_text(encoding='utf-8')
    assert source.count('INSERT INTO receipt_table_lines') == 2
    assert source.count('line_role, inventory_eligible') == 2
    assert source.count('semantics = derive_receipt_line_semantics(line, store_name=parse_result.store_name)') == 2
    assert source.count("'line_role': semantics['line_role']") == 2
    assert source.count("'inventory_eligible': 1 if semantics['inventory_eligible'] else 0") == 2
