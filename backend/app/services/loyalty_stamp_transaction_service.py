from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import text

from app.receipt_ingestion.spaarzegels_terms import is_spaarzegels_flow_excluded


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _stamp_program_code(store_name: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", _text(store_name).lower()).strip("_")
    return f"{normalized or 'unknown'}_spaarzegels"


def ensure_loyalty_stamp_transactions_schema(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS loyalty_stamp_transactions (
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
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_loyalty_stamp_transactions_receipt_line
            ON loyalty_stamp_transactions (receipt_line_id)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_loyalty_stamp_transactions_household_store
            ON loyalty_stamp_transactions (household_id, store_name, purchase_at)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_loyalty_stamp_transactions_receipt_table
            ON loyalty_stamp_transactions (receipt_table_id)
            """
        )
    )


def _spaarzegels_transaction_rows(conn, receipt_table_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT
                rt.household_id,
                rt.id AS receipt_table_id,
                rt.store_name,
                rt.purchase_at,
                rtl.id AS receipt_line_id,
                rtl.raw_label,
                rtl.normalized_label,
                TRIM(COALESCE(CAST(rtl.quantity AS TEXT), '') || ' ' || COALESCE(CAST(rtl.unit AS TEXT), '')) AS quantity_label,
                rtl.quantity,
                rtl.unit_price,
                rtl.line_total
            FROM receipt_table_lines rtl
            JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
            WHERE rtl.receipt_table_id = :receipt_table_id
            ORDER BY rtl.line_index ASC, rtl.id ASC
            """
        ),
        {"receipt_table_id": _text(receipt_table_id)},
    ).mappings().all()

    transaction_rows: list[dict[str, Any]] = []
    for row in rows:
        row_data = dict(row)
        if not is_spaarzegels_flow_excluded({
            "receipt_line_text": row_data.get("raw_label") or row_data.get("normalized_label"),
            "raw_label": row_data.get("raw_label"),
            "normalized_label": row_data.get("normalized_label"),
            "quantity_label": row_data.get("quantity_label"),
            "quantity": row_data.get("quantity"),
            "unit_price": row_data.get("unit_price"),
            "line_total": row_data.get("line_total"),
            "price": row_data.get("line_total"),
        }):
            continue
        transaction_rows.append({
            "id": uuid.uuid4().hex,
            "household_id": _text(row_data.get("household_id")),
            "receipt_table_id": _text(row_data.get("receipt_table_id")),
            "receipt_line_id": _text(row_data.get("receipt_line_id")),
            "store_name": _text(row_data.get("store_name")) or None,
            "stamp_program_code": _stamp_program_code(row_data.get("store_name")),
            "quantity": _number(row_data.get("quantity")),
            "unit_price": _number(row_data.get("unit_price")),
            "line_total": _number(row_data.get("line_total")),
            "transaction_type": "purchase",
            "source": "receipt_table_line",
            "purchase_at": _text(row_data.get("purchase_at")) or None,
        })
    return transaction_rows


def sync_loyalty_stamp_transactions_for_receipt_table(conn, receipt_table_id: str) -> dict[str, Any]:
    normalized_receipt_table_id = _text(receipt_table_id)
    if not normalized_receipt_table_id:
        return {"ok": True, "receipt_table_id": "", "transaction_count": 0, "deleted_count": 0, "inserted_count": 0}

    ensure_loyalty_stamp_transactions_schema(conn)
    rows = _spaarzegels_transaction_rows(conn, normalized_receipt_table_id)

    existing = conn.execute(
        text("SELECT COUNT(*) AS total FROM loyalty_stamp_transactions WHERE receipt_table_id = :receipt_table_id"),
        {"receipt_table_id": normalized_receipt_table_id},
    ).mappings().first()
    deleted_count = int((existing or {}).get("total") or 0)

    conn.execute(
        text("DELETE FROM loyalty_stamp_transactions WHERE receipt_table_id = :receipt_table_id"),
        {"receipt_table_id": normalized_receipt_table_id},
    )

    if rows:
        conn.execute(
            text(
                """
                INSERT INTO loyalty_stamp_transactions (
                    id, household_id, receipt_table_id, receipt_line_id, store_name, stamp_program_code,
                    quantity, unit_price, line_total, transaction_type, source, purchase_at
                ) VALUES (
                    :id, :household_id, :receipt_table_id, :receipt_line_id, :store_name, :stamp_program_code,
                    :quantity, :unit_price, :line_total, :transaction_type, :source, :purchase_at
                )
                """
            ),
            rows,
        )

    return {
        "ok": True,
        "receipt_table_id": normalized_receipt_table_id,
        "transaction_count": len(rows),
        "deleted_count": deleted_count,
        "inserted_count": len(rows),
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "creates_external_database_candidate": False,
    }
