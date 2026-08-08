"""
Self-contained no-OCR validation for receipt reparse header preservation.

Purpose:
- Prove that reparse_receipt keeps existing receipt_tables header fields when
  parse_receipt_content returns None for those fields.
- Do not run PaddleOCR/Tesseract/OCR.
- Do not depend on real AH photo receipts.

Expected success marker:
HEADER_PRESERVATION_OK
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, text

import app.services.receipt_service as receipt_service


def _create_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE raw_receipts (
                    id TEXT PRIMARY KEY,
                    household_id TEXT,
                    original_filename TEXT,
                    mime_type TEXT,
                    storage_path TEXT,
                    raw_status TEXT,
                    deleted_at TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE receipt_tables (
                    id TEXT PRIMARY KEY,
                    raw_receipt_id TEXT,
                    household_id TEXT,
                    store_name TEXT,
                    store_branch TEXT,
                    purchase_at TEXT,
                    total_amount REAL,
                    discount_total REAL,
                    currency TEXT,
                    parse_status TEXT,
                    confidence_score REAL,
                    line_count INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE receipt_table_lines (
                    id TEXT PRIMARY KEY,
                    receipt_table_id TEXT,
                    line_index INTEGER,
                    raw_label TEXT,
                    normalized_label TEXT,
                    quantity REAL,
                    unit TEXT,
                    unit_price REAL,
                    line_total REAL,
                    discount_amount REAL,
                    barcode TEXT,
                    article_match_status TEXT,
                    matched_article_id TEXT,
                    confidence_score REAL,
                    is_deleted INTEGER DEFAULT 0
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE receipt_email_messages (
                    raw_receipt_id TEXT,
                    body_html TEXT,
                    body_text TEXT,
                    selected_part_type TEXT
                )
                """
            )
        )


def _seed_receipt(engine, storage_root: Path, receipt_table_id: str) -> None:
    raw_receipt_id = "raw-" + receipt_table_id
    source_path = storage_root / "source.txt"
    source_path.write_text("fake receipt source for no-ocr self-test", encoding="utf-8")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO raw_receipts (
                    id, household_id, original_filename, mime_type, storage_path, raw_status, deleted_at
                ) VALUES (
                    :id, '1', 'source.txt', 'text/plain', :storage_path, 'parsed', NULL
                )
                """
            ),
            {"id": raw_receipt_id, "storage_path": str(source_path)},
        )
        conn.execute(
            text(
                """
                INSERT INTO receipt_tables (
                    id,
                    raw_receipt_id,
                    household_id,
                    store_name,
                    store_branch,
                    purchase_at,
                    total_amount,
                    discount_total,
                    currency,
                    parse_status,
                    confidence_score,
                    line_count,
                    deleted_at
                ) VALUES (
                    :id,
                    :raw_receipt_id,
                    '1',
                    'Albert Heijn',
                    'Fortunastraat 17, Arnhem',
                    '2026-07-06T00:00:00',
                    81.25,
                    -0.99,
                    'EUR',
                    'parsed',
                    0.36,
                    1,
                    NULL
                )
                """
            ),
            {"id": receipt_table_id, "raw_receipt_id": raw_receipt_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO receipt_table_lines (
                    id,
                    receipt_table_id,
                    line_index,
                    raw_label,
                    normalized_label,
                    quantity,
                    unit,
                    unit_price,
                    line_total,
                    discount_amount,
                    barcode,
                    article_match_status,
                    matched_article_id,
                    confidence_score,
                    is_deleted
                ) VALUES (
                    :id,
                    :receipt_table_id,
                    0,
                    'OLD LINE',
                    'old line',
                    1,
                    'stuk',
                    1.00,
                    1.00,
                    0,
                    NULL,
                    'unmatched',
                    NULL,
                    0.10,
                    0
                )
                """
            ),
            {"id": str(uuid.uuid4()), "receipt_table_id": receipt_table_id},
        )


def _fake_parse_receipt_content(raw_bytes, filename, mime_type):
    return SimpleNamespace(
        is_receipt=True,
        parse_status="parsed",
        confidence_score=0.99,
        store_name=None,
        store_branch=None,
        purchase_at=None,
        total_amount=None,
        discount_total=None,
        currency=None,
        lines=[
            {
                "raw_label": "NEW HEADER PRESERVATION LINE",
                "normalized_label": "new header preservation line",
                "quantity": 1,
                "unit": "stuk",
                "unit_price": 82.24,
                "line_total": 82.24,
                "discount_amount": 0,
                "barcode": None,
                "confidence_score": 0.99,
            }
        ],
    )


def main() -> None:
    original_parser = receipt_service.parse_receipt_content
    receipt_service.parse_receipt_content = _fake_parse_receipt_content

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            engine = create_engine(f"sqlite:///{root / 'selftest.db'}", future=True)
            receipt_table_id = "selftest-receipt"

            _create_schema(engine)
            _seed_receipt(engine, root, receipt_table_id)

            result = receipt_service.reparse_receipt(engine, root, receipt_table_id)
            if not result:
                raise SystemExit("REPARSE_RETURNED_EMPTY")

            with engine.begin() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT
                            store_name,
                            store_branch,
                            purchase_at,
                            total_amount,
                            discount_total,
                            currency,
                            line_count
                        FROM receipt_tables
                        WHERE id = :id
                        """
                    ),
                    {"id": receipt_table_id},
                ).mappings().first()
                lines = conn.execute(
                    text(
                        """
                        SELECT raw_label, line_total
                        FROM receipt_table_lines
                        WHERE receipt_table_id = :id
                        ORDER BY line_index
                        """
                    ),
                    {"id": receipt_table_id},
                ).mappings().all()

            if not row:
                raise SystemExit("RECEIPT_ROW_MISSING")
            if row["store_name"] != "Albert Heijn":
                raise SystemExit(f"STORE_NAME_NOT_PRESERVED: {row['store_name']}")
            if row["store_branch"] != "Fortunastraat 17, Arnhem":
                raise SystemExit(f"STORE_BRANCH_NOT_PRESERVED: {row['store_branch']}")
            if row["purchase_at"] != "2026-07-06T00:00:00":
                raise SystemExit(f"PURCHASE_AT_NOT_PRESERVED: {row['purchase_at']}")
            if float(row["total_amount"]) != 81.25:
                raise SystemExit(f"TOTAL_AMOUNT_NOT_PRESERVED: {row['total_amount']}")
            if float(row["discount_total"]) != -0.99:
                raise SystemExit(f"DISCOUNT_TOTAL_NOT_PRESERVED: {row['discount_total']}")
            if row["currency"] != "EUR":
                raise SystemExit(f"CURRENCY_NOT_PRESERVED: {row['currency']}")
            if int(row["line_count"]) != 1:
                raise SystemExit(f"LINE_COUNT_UNEXPECTED: {row['line_count']}")
            if len(lines) != 1 or lines[0]["raw_label"] != "NEW HEADER PRESERVATION LINE":
                raise SystemExit(f"NEW_LINES_NOT_STORED: {lines}")

            print("HEADER_PRESERVATION_OK")
    finally:
        receipt_service.parse_receipt_content = original_parser


if __name__ == "__main__":
    main()
