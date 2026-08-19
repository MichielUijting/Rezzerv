from pathlib import Path

from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics


def test_canonical_product_is_inventory_product():
    result = derive_receipt_line_semantics({
        'line_type': 'product',
        'raw_label': 'opaque product label',
    })
    assert result == {'line_role': 'product', 'inventory_eligible': True}


def test_canonical_loyalty_is_not_inventory():
    result = derive_receipt_line_semantics({
        'line_type': 'loyalty',
        'raw_label': 'opaque loyalty label',
    })
    assert result == {'line_role': 'loyalty', 'inventory_eligible': False}


def test_canonical_financial_types_are_not_inventory():
    for line_type in ('discount', 'deposit', 'shipping', 'fee', 'tax', 'payment', 'total'):
        result = derive_receipt_line_semantics({
            'line_type': line_type,
            'raw_label': f'opaque {line_type} label',
        })
        assert result['line_role'] == 'financial', line_type
        assert result['inventory_eligible'] is False, line_type


def test_untyped_line_fails_closed():
    result = derive_receipt_line_semantics({'raw_label': 'Onbekende tekst'})
    assert result == {'line_role': 'unknown', 'inventory_eligible': False}


def test_persisted_semantics_are_authoritative():
    result = derive_receipt_line_semantics({
        'line_type': 'product',
        'raw_label': 'arbitrary display text',
        'line_role': 'loyalty',
        'inventory_eligible': 0,
    })
    assert result == {'line_role': 'loyalty', 'inventory_eligible': False}


def test_semantic_columns_live_in_central_receipt_schema_evolution():
    source = (Path(__file__).resolve().parents[1] / 'app/main.py').read_text(encoding='utf-8')
    start = source.index('line_additions = {')
    block = source[start:start + 1200]
    assert "'line_role': 'TEXT'" in block
    assert "'inventory_eligible': 'INTEGER'" in block


def test_receipt_service_persists_semantics_on_both_ingest_paths():
    source = (Path(__file__).resolve().parents[1] / 'app/services/receipt_service.py').read_text(encoding='utf-8')
    assert source.count('INSERT INTO receipt_table_lines') == 2
    assert source.count('line_role, inventory_eligible') == 2
    assert source.count('semantics = derive_receipt_line_semantics(line, store_name=parse_result.store_name)') == 2
    assert source.count("'line_role': semantics['line_role']") == 2
    assert source.count("'inventory_eligible': 1 if semantics['inventory_eligible'] else 0") == 2
