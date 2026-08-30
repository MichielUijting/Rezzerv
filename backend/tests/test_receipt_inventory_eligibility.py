import gzip
import sqlite3
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


def test_semantic_columns_live_in_migration_owned_receipt_schema():
    backend_root = Path(__file__).resolve().parents[1]
    baseline_path = backend_root / 'alembic/baseline_sqlite.sql.gz'
    authority_path = backend_root / 'alembic/versions/20260828_02_receipt_lifecycle_schema_authority.py'

    connection = sqlite3.connect(':memory:')
    try:
        with gzip.open(baseline_path, 'rt', encoding='utf-8') as handle:
            connection.executescript(handle.read())
        columns = {
            str(row[1]): str(row[2] or '').upper()
            for row in connection.execute('PRAGMA table_info("receipt_table_lines")').fetchall()
        }
    finally:
        connection.close()

    assert columns['line_role'] == 'TEXT'
    assert columns['inventory_eligible'] == 'INTEGER'

    authority_source = authority_path.read_text(encoding='utf-8')
    assert 'receipt_table_lines' in authority_source
    assert '_validate_sqlite' in authority_source
    assert '_validate_postgresql' in authority_source


def test_receipt_service_persists_semantics_on_both_ingest_paths():
    source = (Path(__file__).resolve().parents[1] / 'app/services/receipt_service.py').read_text(encoding='utf-8')
    assert source.count('INSERT INTO receipt_table_lines') == 2
    assert source.count('line_role, inventory_eligible') == 2
    assert source.count('semantics = derive_receipt_line_semantics(line, store_name=parse_result.store_name)') == 2
    assert source.count("'line_role': semantics['line_role']") == 2
    assert source.count("'inventory_eligible': 1 if semantics['inventory_eligible'] else 0") == 2
