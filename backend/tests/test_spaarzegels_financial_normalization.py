from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.receipt_ingestion.product_candidate_gateway import append_product_candidate
from app.receipt_ingestion.spaarzegels_terms import (
    is_spaarzegels_financial_pair,
    is_spaarzegels_flow_excluded,
    spaarzegels_financial_metadata,
)
from app.services.external_database_matchflow_evidence import _filter_external_matching_items
from app.services.loyalty_stamp_transaction_service import sync_loyalty_stamp_transactions_for_receipt_table


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _parse_quantity(value: str | None):
    if value is None or value == "":
        return None
    return Decimal(str(value).replace(",", "."))


def _parse_decimal(value: str | None):
    if value is None or value == "":
        return None
    return Decimal(str(value).replace(",", ".")).quantize(Decimal("0.01"))


def _amount_to_float(value):
    if value is None:
        return None
    return float(value)


def _classify(_value: str) -> str:
    return "product_candidate"


def _spaarzegels_line() -> dict:
    extracted: list[dict] = []

    appended_index = append_product_candidate(
        extracted,
        label="Koopzegels",
        qty_raw="2",
        amount1_raw="0.10",
        amount2_raw="0.20",
        source_index=12,
        raw_line="2 x 0.10 0.20",
        normalized_line="2 x 0.10 0.20",
        filename="jumbo-app.txt",
        store_name="Jumbo",
        function_name="_extract_savings_action_lines",
        append_branch="savings_action_line",
        parser_path="test.spaarzegels_pair",
        caller_line_hint="test spaarzegels detail pair",
        clean_label=_clean,
        parse_quantity=_parse_quantity,
        parse_decimal=_parse_decimal,
        amount_to_float=_amount_to_float,
        classify_line=_classify,
    )

    assert appended_index == 0
    assert len(extracted) == 1
    return extracted[0]


def test_spaarzegels_financial_pair_combines_label_and_detail_line():
    assert is_spaarzegels_financial_pair(
        label_text="Koopzegels",
        detail_text="2 x 0.10 0.20",
    )

    metadata = spaarzegels_financial_metadata(
        label_text="Koopzegels",
        detail_text="2 x 0.10 0.20",
    )

    assert metadata["line_type"] == "spaarzegels"
    assert metadata["include_in_receipt_total"] is True
    assert metadata["exclude_from_inventory"] is True
    assert metadata["external_matching_allowed"] is False


def test_gateway_preserves_quantity_unit_price_total_for_spaarzegels_pair():
    line = _spaarzegels_line()

    assert line["quantity"] == 2.0
    assert line["unit_price"] == 0.10
    assert line["line_total"] == 0.20
    assert line["line_type"] == "spaarzegels"
    assert line["include_in_receipt_total"] is True
    assert line["exclude_from_inventory"] is True
    assert line["external_matching_allowed"] is False

    trace = line["producer_trace"]
    assert trace["line_type"] == "spaarzegels"
    assert trace["external_matching_allowed"] is False


def test_spaarzegels_are_excluded_from_external_database_items():
    spaarzegels_line = _spaarzegels_line()
    product_line = {
        "receipt_line_id": "product-1",
        "receipt_line_text": "Halfvolle melk",
        "raw_label": "Halfvolle melk",
        "normalized_label": "Halfvolle melk",
        "line_total": 1.29,
        "unit_price": 1.29,
        "price": 1.29,
    }

    external_items = [
        {
            "receipt_line_id": "spaarzegels-1",
            "receipt_line_text": spaarzegels_line["raw_label"],
            "raw_label": spaarzegels_line["raw_label"],
            "normalized_label": spaarzegels_line["normalized_label"],
            "quantity_label": str(spaarzegels_line["quantity"]),
            "unit_price": spaarzegels_line["unit_price"],
            "line_total": spaarzegels_line["line_total"],
            "price": spaarzegels_line["line_total"],
            "line_type": spaarzegels_line["line_type"],
            "is_spaarzegels": spaarzegels_line["is_spaarzegels"],
            "external_matching_allowed": spaarzegels_line["external_matching_allowed"],
        },
        product_line,
    ]

    assert is_spaarzegels_flow_excluded(external_items[0]) is True
    assert is_spaarzegels_flow_excluded(product_line) is False

    filtered_items = _filter_external_matching_items(external_items)

    assert filtered_items == [product_line]


def test_spaarzegels_transactions_are_stored_idempotently():
    db = create_engine("sqlite:///:memory:")
    with db.begin() as conn:
        conn.execute(text("""
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                store_name TEXT,
                purchase_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE receipt_table_lines (
                id TEXT PRIMARY KEY,
                receipt_table_id TEXT NOT NULL,
                line_index INTEGER,
                raw_label TEXT,
                normalized_label TEXT,
                quantity REAL,
                unit TEXT,
                unit_price REAL,
                line_total REAL
            )
        """))
        conn.execute(
            text("""
                INSERT INTO receipt_tables (id, household_id, store_name, purchase_at)
                VALUES ('rt1', '1', 'Jumbo', '2026-06-28')
            """),
        )
        conn.execute(
            text("""
                INSERT INTO receipt_table_lines (
                    id, receipt_table_id, line_index, raw_label, normalized_label, quantity, unit, unit_price, line_total
                ) VALUES
                    ('rtl-spaarzegels', 'rt1', 1, 'Koopzegels', 'Koopzegels', 2, NULL, 0.10, 0.20),
                    ('rtl-product', 'rt1', 2, 'Halfvolle melk', 'Halfvolle melk', 1, NULL, 1.29, 1.29)
            """),
        )

        first = sync_loyalty_stamp_transactions_for_receipt_table(conn, 'rt1')
        second = sync_loyalty_stamp_transactions_for_receipt_table(conn, 'rt1')

        rows = conn.execute(
            text("SELECT * FROM loyalty_stamp_transactions ORDER BY receipt_line_id")
        ).mappings().all()

    assert first["transaction_count"] == 1
    assert second["transaction_count"] == 1
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["receipt_line_id"] == "rtl-spaarzegels"
    assert row["household_id"] == "1"
    assert row["store_name"] == "Jumbo"
    assert row["stamp_program_code"] == "jumbo_spaarzegels"
    assert row["quantity"] == 2.0
    assert row["unit_price"] == 0.10
    assert row["line_total"] == 0.20
    assert row["transaction_type"] == "purchase"
    assert row["source"] == "receipt_table_line"


if __name__ == "__main__":
    test_spaarzegels_financial_pair_combines_label_and_detail_line()
    test_gateway_preserves_quantity_unit_price_total_for_spaarzegels_pair()
    test_spaarzegels_are_excluded_from_external_database_items()
    test_spaarzegels_transactions_are_stored_idempotently()
    print("SPAARZEGELS_NORMALIZATION_OK")
