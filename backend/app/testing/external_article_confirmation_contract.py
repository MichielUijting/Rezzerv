"""Geïsoleerd contract voor brononafhankelijke algemene bevestiging."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.external_article_confirmation_service import (
    confirm_external_article_for_receipt_item,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE global_products (id TEXT PRIMARY KEY, name TEXT, status TEXT)"))
        conn.execute(text("INSERT INTO global_products VALUES ('gp-1', 'Testproduct', 'active')"))
        conn.execute(text("""
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY, store_chain TEXT, store_name TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE receipt_table_lines (
                id TEXT PRIMARY KEY, receipt_table_id TEXT, corrected_raw_label TEXT,
                raw_label TEXT, normalized_label TEXT, external_article_code TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_batches (
                id TEXT PRIMARY KEY, source_reference TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_lines (
                id TEXT PRIMARY KEY, batch_id TEXT, article_name_raw TEXT,
                external_article_code TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE external_product_candidates (
                id TEXT PRIMARY KEY, context_key TEXT, purchase_import_line_id TEXT,
                receipt_line_id TEXT, retailer_code TEXT, receipt_line_text TEXT,
                external_article_code TEXT, is_user_confirmed INTEGER,
                global_product_id TEXT, updated_at TEXT, created_at TEXT
            )
        """))
        conn.execute(text("INSERT INTO receipt_tables VALUES ('rt-1', 'ALDI', 'Aldi')"))
        conn.execute(text("INSERT INTO receipt_table_lines VALUES ('rtl-1', 'rt-1', NULL, '7-GRANEN ONTBIJT', NULL, NULL)"))
        conn.execute(text("INSERT INTO purchase_import_batches VALUES ('pb-1', 'receipt:rt-1')"))
        conn.execute(text("INSERT INTO purchase_import_lines VALUES ('pil-1', 'pb-1', '7-GRANEN ONTBIJT', NULL)"))
        conn.execute(text("""
            INSERT INTO external_product_candidates VALUES (
                'cand-preview', 'receipt-line:preview-1', 'preview:receipt-line:preview-1',
                'preview-1', 'aldi', '7-GRANEN ONTBIJT', NULL, 1, 'gp-1',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """))
    return engine


def run_contract() -> None:
    engine = _engine()
    with engine.begin() as conn:
        for receipt_item_id in (
            "receipt-table-line:rtl-1",
            "purchase-import-line:pil-1",
            "receipt-line:preview-1",
        ):
            result = confirm_external_article_for_receipt_item(
                conn,
                receipt_item_id=receipt_item_id,
                global_product_id="gp-1",
                confirmed_by="contract-step-4",
            )
            _assert(result["retailer_code"] == "aldi", f"Winkel niet opgelost voor {receipt_item_id}")
            _assert(
                result["receipt_text_normalized"] == "7 granen ontbijt",
                f"Bontekst niet opgelost voor {receipt_item_id}",
            )

        active = conn.execute(text("""
            SELECT COUNT(*) FROM external_article_product_links
            WHERE retailer_code = 'aldi'
              AND receipt_text_normalized = '7 granen ontbijt'
              AND status = 'confirmed'
        """)).scalar_one()
        _assert(active == 1, "Er is niet precies één actieve algemene koppeling")

    print("PASS: receipt-table-line schrijft centraal")
    print("PASS: purchase-import-line schrijft centraal")
    print("PASS: preview receipt-line schrijft centraal")
    print("PASS: alle routes delen één algemene winkelsleutel")
    print("PASS: precies één actieve koppeling blijft bestaan")


if __name__ == "__main__":
    run_contract()
