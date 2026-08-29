from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.services.loyalty_stamp_read_service import (
    list_loyalty_stamp_programs_for_household,
    list_loyalty_stamp_transactions_for_household,
)


def _create_loyalty_fixture(conn) -> None:
    conn.execute(text("""
        CREATE TABLE loyalty_stamp_transactions (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            receipt_table_id TEXT NOT NULL,
            receipt_line_id TEXT NOT NULL,
            store_name TEXT,
            stamp_program_code TEXT NOT NULL,
            quantity REAL,
            unit_price REAL,
            line_total REAL,
            transaction_type TEXT NOT NULL DEFAULT 'purchase',
            source TEXT NOT NULL DEFAULT 'receipt_table_line',
            purchase_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("""
        CREATE UNIQUE INDEX idx_loyalty_stamp_transactions_receipt_line
        ON loyalty_stamp_transactions (receipt_line_id)
    """))
    conn.execute(text("""
        CREATE INDEX idx_loyalty_stamp_transactions_household_store
        ON loyalty_stamp_transactions (household_id, store_name, purchase_at)
    """))
    conn.execute(text("""
        CREATE INDEX idx_loyalty_stamp_transactions_receipt_table
        ON loyalty_stamp_transactions (receipt_table_id)
    """))


def _seed_transactions(conn) -> None:
    _create_loyalty_fixture(conn)
    conn.execute(
        text(
            """
            INSERT INTO loyalty_stamp_transactions (
                id, household_id, receipt_table_id, receipt_line_id, store_name,
                stamp_program_code, quantity, unit_price, line_total,
                transaction_type, source, purchase_at
            ) VALUES
                ('a1', 'household-a', 'receipt-a1', 'line-a1', 'Jumbo',
                 'jumbo_spaarzegels', 2, 0.10, 0.20, 'purchase',
                 'receipt_table_line', '2026-07-20'),
                ('a2', 'household-a', 'receipt-a2', 'line-a2', 'Jumbo',
                 'jumbo_spaarzegels', 3, 0.10, 0.30, 'purchase',
                 'receipt_table_line', '2026-07-21'),
                ('a3', 'household-a', 'receipt-a3', 'line-a3', 'PLUS',
                 'plus_spaarzegels', 1, 0.05, 0.05, 'purchase',
                 'receipt_table_line', '2026-07-19'),
                ('b1', 'household-b', 'receipt-b1', 'line-b1', 'Jumbo',
                 'jumbo_spaarzegels', 99, 0.10, 9.90, 'purchase',
                 'receipt_table_line', '2026-07-22')
            """
        )
    )


def test_program_projection_is_household_scoped():
    db = create_engine('sqlite:///:memory:')
    with db.begin() as conn:
        _seed_transactions(conn)
        programs = list_loyalty_stamp_programs_for_household(conn, 'household-a')

    assert len(programs) == 2
    jumbo = next(item for item in programs if item['stamp_program_code'] == 'jumbo_spaarzegels')
    assert jumbo['store_name'] == 'Jumbo'
    assert jumbo['purchased_quantity'] == 5.0
    assert jumbo['paid_amount'] == 0.50
    assert jumbo['transaction_count'] == 2
    assert jumbo['last_transaction_at'] == '2026-07-21'
    assert all(item['paid_amount'] < 9.90 for item in programs)


def test_transaction_detail_is_household_scoped_and_program_filterable():
    db = create_engine('sqlite:///:memory:')
    with db.begin() as conn:
        _seed_transactions(conn)
        transactions = list_loyalty_stamp_transactions_for_household(
            conn,
            'household-a',
            stamp_program_code='jumbo_spaarzegels',
            limit=10,
        )

    assert [row['id'] for row in transactions] == ['a2', 'a1']
    assert all(row['stamp_program_code'] == 'jumbo_spaarzegels' for row in transactions)
    assert all(row['id'] != 'b1' for row in transactions)


def test_empty_household_identifier_returns_no_data():
    db = create_engine('sqlite:///:memory:')
    with db.begin() as conn:
        _seed_transactions(conn)
        assert list_loyalty_stamp_programs_for_household(conn, '') == []
        assert list_loyalty_stamp_transactions_for_household(conn, '') == []