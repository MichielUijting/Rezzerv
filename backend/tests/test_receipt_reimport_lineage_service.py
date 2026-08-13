import sqlite3

from sqlalchemy import create_engine, text

from app.services.receipt_reimport_lineage_service import (
    load_deleted_reimport_lineage,
    resolve_reimport_logical_line_key,
)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE raw_receipts (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                sha256_hash TEXT NOT NULL,
                deleted_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                raw_receipt_id TEXT NOT NULL,
                logical_receipt_key TEXT,
                workflow_state TEXT NOT NULL DEFAULT 'active',
                deleted_at DATETIME,
                updated_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE receipt_table_lines (
                id TEXT PRIMARY KEY,
                receipt_table_id TEXT NOT NULL,
                line_index INTEGER NOT NULL,
                raw_label TEXT,
                normalized_label TEXT,
                quantity NUMERIC,
                unit TEXT,
                unit_price NUMERIC,
                line_total NUMERIC,
                logical_line_key TEXT,
                created_at DATETIME
            )
        """))
    return engine


def test_reimport_lineage_reuses_exact_receipt_and_line_keys_only():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO raw_receipts VALUES ('raw-old','0','abc',CURRENT_TIMESTAMP)"))
        conn.execute(text("""
            INSERT INTO receipt_tables
                (id, raw_receipt_id, logical_receipt_key, workflow_state, deleted_at, updated_at)
            VALUES
                ('receipt-old','raw-old','receipt-key','removed_reimport_allowed',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        """))
        conn.execute(text("""
            INSERT INTO receipt_table_lines
                (id, receipt_table_id, line_index, raw_label, normalized_label, quantity, unit, unit_price, line_total, logical_line_key, created_at)
            VALUES
                ('line-old','receipt-old',0,'Melk','melk',1,'liter',1.25,1.25,'line-key',CURRENT_TIMESTAMP)
        """))

        lineage = load_deleted_reimport_lineage(conn, '0', 'abc')

    assert lineage is not None
    assert lineage['receipt_table_id'] == 'receipt-old'
    assert lineage['logical_receipt_key'] == 'receipt-key'
    assert resolve_reimport_logical_line_key(
        lineage,
        0,
        {'raw_label': 'Melk', 'normalized_label': 'melk', 'quantity': 1, 'unit': 'liter', 'unit_price': 1.25, 'line_total': 1.25},
    ) == 'line-key'
    assert resolve_reimport_logical_line_key(
        lineage,
        0,
        {'raw_label': 'Melk', 'normalized_label': 'melk', 'quantity': 2, 'unit': 'liter', 'unit_price': 1.25, 'line_total': 2.50},
    ) is None


def test_non_reimportable_deleted_receipt_is_not_lineage_source():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO raw_receipts VALUES ('raw-old','0','abc',CURRENT_TIMESTAMP)"))
        conn.execute(text("""
            INSERT INTO receipt_tables
                (id, raw_receipt_id, logical_receipt_key, workflow_state, deleted_at, updated_at)
            VALUES
                ('receipt-old','raw-old','receipt-key','legacy_deleted',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        """))
        assert load_deleted_reimport_lineage(conn, '0', 'abc') is None
