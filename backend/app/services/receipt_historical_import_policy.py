"""Fail-closed receipt-history boundary for new opted-in households.

No cutover row means legacy behavior. This module never infers household
identity from receipt content or from an untrusted client-supplied query value.
Purchase DATE is compared with the first calendar date of live use. Same-day
purchases are intentionally 'current'; time-of-day partitioning is not proven
by existing retailer receipt timestamps and must not be invented.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import text

_IMPORT_DEFAULT = "import_default"


def _date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    raw = str(value).strip()
    try:
        # Receipt timestamps are stored without a reliable time-zone contract.
        return date.fromisoformat(raw[:10])
    except (TypeError, ValueError):
        return None


def classify_purchase_date(
    purchase_at, *, purchase_at_source: str | None, first_current_purchase_date,
) -> str:
    """Pure classifier; no client-controlled 'historical' override."""
    cutoff = _date(first_current_purchase_date)
    if cutoff is None:
        return "legacy"
    if str(purchase_at_source or "").strip().lower() == _IMPORT_DEFAULT:
        return "review_required"
    purchased = _date(purchase_at)
    if purchased is None:
        return "review_required"
    return "historical" if purchased < cutoff else "current"


def read_household_cutover(conn, household_id: str) -> date | None:
    if not str(household_id or "").strip():
        raise ValueError("Actief huishouden ontbreekt")
    raw = conn.execute(text("""
        SELECT first_current_purchase_date
        FROM household_receipt_history_cutovers
        WHERE household_id = :household_id
    """), {"household_id": str(household_id)}).scalar_one_or_none()
    return _date(raw)


def classify_receipt_for_household(
    conn, *, household_id: str, receipt_table_id: str,
) -> str:
    """Classification is derived from canonical receipt data and household key."""
    cutoff = read_household_cutover(conn, household_id)
    if cutoff is None:
        return "legacy"
    row = conn.execute(text("""
        SELECT purchase_at, purchase_at_source
        FROM receipt_tables
        WHERE id = :receipt_table_id
          AND household_id = :household_id
          AND deleted_at IS NULL
        LIMIT 1
    """), {
        "receipt_table_id": str(receipt_table_id),
        "household_id": str(household_id),
    }).mappings().first()
    if not row:
        return "review_required"
    return classify_purchase_date(
        row["purchase_at"],
        purchase_at_source=row["purchase_at_source"],
        first_current_purchase_date=cutoff,
    )


def require_batch_inventory_allowed(
    conn, *, household_id: str, batch_id: str,
) -> None:
    """Guard both direct Kassa approvals and later Uitpakken batch processing.

    The process caller must first authorize the household server-side.
    Non-receipt purchase batches retain their existing handling.
    """
    row = conn.execute(text("""
        SELECT source_type, source_reference
        FROM purchase_import_batches
        WHERE id = :batch_id AND household_id = :household_id
        LIMIT 1
    """), {"batch_id": str(batch_id), "household_id": str(household_id)}).mappings().first()
    if not row or str(row["source_type"] or "") != "receipt":
        return
    ref = str(row["source_reference"] or "")
    if not ref.startswith("receipt:") or not ref.removeprefix("receipt:"):
        disposition = "review_required" if read_household_cutover(conn, household_id) else "legacy"
    else:
        disposition = classify_receipt_for_household(
            conn, household_id=household_id,
            receipt_table_id=ref.removeprefix("receipt:"),
        )
    if disposition == "historical":
        raise HTTPException(
            status_code=409,
            detail="Historische kassabonnen blijven voor aankoopanalyse bewaard en mogen niet naar Voorraad.",
        )
    if disposition == "review_required":
        raise HTTPException(
            status_code=409,
            detail="Controleer eerst de oorspronkelijke aankoopdatum; er is niets naar Voorraad geboekt.",
        )


def activate_cutover_for_new_onboarding(
    conn, *, household_id: str,
) -> bool:
    """Initialize a cutover during the *first* authorized onboarding completion.

    Caller must have confirmed the canonical household-settings permission and
    the ongoing initial onboarding step. This function does not expose a route
    and cannot be invoked by a receipt payload. We do not reclassify a household
    that already has any receipts or inventory facts: that would be unsafe.
    The transaction is supplied by the caller, so completion and activation
    commit or roll back as a unit.

    The start is the database server's current calendar date. No timestamp
    guesswork or client clock is used.
    """
    normalized = str(household_id or "").strip()
    if not normalized or normalized == "0":
        raise ValueError("Historische ontvangstgrens vereist een regulier huishouden")
    existing = read_household_cutover(conn, normalized)
    if existing is not None:
        return False

    for table in (
        "raw_receipts",
        "receipt_tables",
        "purchase_import_batches",
        "inventory_events",
        "inventory",
    ):
        has_records = conn.execute(text(
            f"SELECT 1 FROM {table} WHERE household_id = :household_id LIMIT 1"
        ), {"household_id": normalized}).scalar_one_or_none()
        if has_records is not None:
            # Existing households are intentionally not backfilled or altered.
            return False

    inserted = conn.execute(text("""
        INSERT INTO household_receipt_history_cutovers (
            household_id, first_current_purchase_date
        )
        VALUES (:household_id, CURRENT_DATE)
        ON CONFLICT (household_id) DO NOTHING
    """), {"household_id": normalized})
    return inserted.rowcount == 1
