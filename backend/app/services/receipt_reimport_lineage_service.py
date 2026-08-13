"""Release B receipt reimport lineage helpers.

Uses existing receipt and unpack/inventory facts only. No parallel ledger is
introduced. A deleted receipt with workflow_state=removed_reimport_allowed may
lend its logical receipt/line keys to a later exact-source reimport.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _norm_number(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, ValueError, TypeError):
        return str(value).strip()


def receipt_line_signature(line_index: int, line: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(int(line_index)),
        _norm_text(line.get("normalized_label") or line.get("raw_label")),
        _norm_number(line.get("quantity")),
        _norm_text(line.get("unit")),
        _norm_number(line.get("unit_price")),
        _norm_number(line.get("line_total")),
    )


def load_deleted_reimport_lineage(conn, household_id: str, sha256_hash: str) -> dict[str, Any] | None:
    """Return the most recent explicitly reimportable exact-source receipt."""
    row = conn.execute(
        text(
            """
            SELECT rt.id AS receipt_table_id, rt.logical_receipt_key
            FROM raw_receipts rr
            JOIN receipt_tables rt ON rt.raw_receipt_id = rr.id
            WHERE rr.household_id = :household_id
              AND rr.sha256_hash = :sha256_hash
              AND rr.deleted_at IS NOT NULL
              AND rt.deleted_at IS NOT NULL
              AND rt.workflow_state = 'removed_reimport_allowed'
              AND COALESCE(TRIM(rt.logical_receipt_key), '') <> ''
            ORDER BY datetime(rt.deleted_at) DESC, datetime(rt.updated_at) DESC, rt.id DESC
            LIMIT 1
            """
        ),
        {"household_id": str(household_id), "sha256_hash": str(sha256_hash)},
    ).mappings().first()
    if not row:
        return None

    lines = conn.execute(
        text(
            """
            SELECT line_index, raw_label, normalized_label, quantity, unit,
                   unit_price, line_total, logical_line_key,
                   COALESCE(is_validated, 0) AS is_validated
            FROM receipt_table_lines
            WHERE receipt_table_id = :receipt_table_id
              AND COALESCE(TRIM(logical_line_key), '') <> ''
            ORDER BY line_index ASC, created_at ASC, id ASC
            """
        ),
        {"receipt_table_id": str(row["receipt_table_id"])},
    ).mappings().all()

    by_signature: dict[tuple[str, ...], dict[str, Any] | None] = {}
    for old_line in lines:
        signature = receipt_line_signature(int(old_line.get("line_index") or 0), dict(old_line))
        fact = {
            "logical_line_key": str(old_line.get("logical_line_key") or ""),
            "is_validated": bool(old_line.get("is_validated")),
        }
        # Reuse only an unambiguous exact signature. If the same signature occurs
        # more than once, do not guess which historic line it represents.
        if signature in by_signature:
            by_signature[signature] = None
        else:
            by_signature[signature] = fact

    return {
        "receipt_table_id": str(row["receipt_table_id"]),
        "logical_receipt_key": str(row["logical_receipt_key"]),
        "line_facts_by_signature": {
            key: value for key, value in by_signature.items() if value is not None
        },
    }


def _lineage_line_fact(lineage: dict[str, Any] | None, line_index: int, line: dict[str, Any]) -> dict[str, Any] | None:
    if not lineage:
        return None
    fact = (lineage.get("line_facts_by_signature") or {}).get(receipt_line_signature(line_index, line))
    return dict(fact) if isinstance(fact, dict) else None


def resolve_reimport_logical_line_key(lineage: dict[str, Any] | None, line_index: int, line: dict[str, Any]) -> str | None:
    fact = _lineage_line_fact(lineage, line_index, line)
    return str((fact or {}).get("logical_line_key") or "").strip() or None


def was_prior_line_validated(lineage: dict[str, Any] | None, line_index: int, line: dict[str, Any]) -> bool:
    """Return the existing Kassa approval fact for an exact logical-line match."""
    fact = _lineage_line_fact(lineage, line_index, line)
    return bool((fact or {}).get("is_validated"))


def get_prior_processed_line_fact(conn, logical_line_key: str | None, *, current_receipt_table_id: str | None = None) -> dict[str, Any] | None:
    """Return the existing processing fact for this logical receipt line.

    purchase_import_lines remains the work-state truth and inventory_events remains
    the inventory-effect truth. This helper only resolves those existing facts; it
    creates no copy or ledger.
    """
    normalized_key = str(logical_line_key or "").strip()
    if not normalized_key:
        return None
    params = {
        "logical_line_key": normalized_key,
        "current_receipt_table_id": str(current_receipt_table_id or "").strip(),
    }
    row = conn.execute(
        text(
            """
            SELECT
                pil.id AS purchase_import_line_id,
                pil.processing_status,
                pil.processed_at,
                pil.processed_event_id,
                rtl.receipt_table_id
            FROM receipt_table_lines rtl
            JOIN purchase_import_batches pib
              ON pib.source_type = 'receipt'
             AND pib.source_reference = ('receipt:' || rtl.receipt_table_id)
            JOIN purchase_import_lines pil
              ON pil.batch_id = pib.id
             AND pil.external_line_ref = ('receipt-line:' || rtl.id)
            WHERE rtl.logical_line_key = :logical_line_key
              AND (:current_receipt_table_id = '' OR rtl.receipt_table_id <> :current_receipt_table_id)
              AND (
                    lower(trim(COALESCE(pil.processing_status, ''))) = 'processed'
                 OR COALESCE(trim(pil.processed_event_id), '') <> ''
              )
            ORDER BY datetime(COALESCE(pil.processed_at, pil.created_at)) DESC, pil.id DESC
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    if not row:
        return None
    return dict(row)
