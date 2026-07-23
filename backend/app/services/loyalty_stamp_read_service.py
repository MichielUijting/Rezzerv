from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.services.loyalty_stamp_transaction_service import ensure_loyalty_stamp_transactions_schema


def _text(value: Any) -> str:
    return str(value or "").strip()


def list_loyalty_stamp_programs_for_household(conn, household_id: str) -> list[dict[str, Any]]:
    """Return purchased stamp quantities and paid amounts for one household only."""
    normalized_household_id = _text(household_id)
    if not normalized_household_id:
        return []

    ensure_loyalty_stamp_transactions_schema(conn)
    rows = conn.execute(
        text(
            """
            SELECT
                store_name,
                stamp_program_code,
                COALESCE(SUM(quantity), 0) AS purchased_quantity,
                COALESCE(SUM(line_total), 0) AS paid_amount,
                COUNT(*) AS transaction_count,
                MAX(COALESCE(purchase_at, created_at)) AS last_transaction_at
            FROM loyalty_stamp_transactions
            WHERE household_id = :household_id
              AND transaction_type = 'purchase'
            GROUP BY store_name, stamp_program_code
            ORDER BY MAX(COALESCE(purchase_at, created_at)) DESC,
                     store_name ASC,
                     stamp_program_code ASC
            """
        ),
        {"household_id": normalized_household_id},
    ).mappings().all()

    return [
        {
            "store_name": _text(row.get("store_name")) or None,
            "stamp_program_code": _text(row.get("stamp_program_code")),
            "purchased_quantity": float(row.get("purchased_quantity") or 0),
            "paid_amount": float(row.get("paid_amount") or 0),
            "transaction_count": int(row.get("transaction_count") or 0),
            "last_transaction_at": _text(row.get("last_transaction_at")) or None,
        }
        for row in rows
    ]


def list_loyalty_stamp_transactions_for_household(
    conn,
    household_id: str,
    *,
    stamp_program_code: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return underlying transactions, always filtered by the authorized household."""
    normalized_household_id = _text(household_id)
    normalized_program_code = _text(stamp_program_code)
    normalized_limit = max(1, min(int(limit or 100), 500))
    if not normalized_household_id:
        return []

    ensure_loyalty_stamp_transactions_schema(conn)
    params: dict[str, Any] = {
        "household_id": normalized_household_id,
        "limit": normalized_limit,
    }
    program_filter = ""
    if normalized_program_code:
        program_filter = " AND stamp_program_code = :stamp_program_code"
        params["stamp_program_code"] = normalized_program_code

    rows = conn.execute(
        text(
            f"""
            SELECT
                id,
                receipt_table_id,
                receipt_line_id,
                store_name,
                stamp_program_code,
                quantity,
                unit_price,
                line_total,
                transaction_type,
                source,
                purchase_at,
                created_at
            FROM loyalty_stamp_transactions
            WHERE household_id = :household_id
              {program_filter}
            ORDER BY COALESCE(purchase_at, created_at) DESC,
                     created_at DESC,
                     id DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    return [dict(row) for row in rows]
