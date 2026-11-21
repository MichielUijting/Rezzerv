"""Household-scoped, read-only progress for imported digital receipt history.

Existing receipt and durable queue records are the sole evidence. An acknowledged
browser transfer is NOT a completed Kassa import. This service does not fetch,
reconcile, mutate, approve, or change stock for any household.
"""
from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.platform_feature_flag_service import (
    FEATURE_FLAG_RETAILER_AUTO_IMPORT,
    is_platform_feature_enabled,
)
from app.services.receipt_historical_import_policy import read_household_cutover

_PROVIDERS = (("ah", "Albert Heijn"), ("lidl", "Lidl"), ("jumbo", "Jumbo"))

# Both sides of the join must be scoped to the *authorized* household.
# Receipt date must be the source's original, non-default date. A receipt
# created today but bought before the household cutover is historical.
_RECEIPT_COUNTS_SQL = text("""
    SELECT rr.source_id AS source_id,
           COUNT(DISTINCT rr.id) AS saved_receipts,
           COUNT(DISTINCT rt.id) AS kassa_receipts,
           COUNT(DISTINCT CASE
               WHEN :cutover_enabled = 1
                AND rt.purchase_at IS NOT NULL
                AND LOWER(TRIM(COALESCE(rt.purchase_at_source, ''))) <> 'import_default'
                AND LOWER(TRIM(COALESCE(rt.parse_status, ''))) IN ('parsed', 'approved')
                AND rt.purchase_at < :cutoff_datetime
               THEN rt.id END) AS historical_receipts,
           COUNT(DISTINCT CASE
               WHEN :cutover_enabled = 1
                AND (rt.purchase_at IS NULL
                 OR LOWER(TRIM(COALESCE(rt.purchase_at_source, ''))) = 'import_default'
                 OR LOWER(TRIM(COALESCE(rt.parse_status, ''))) NOT IN ('parsed', 'approved'))
               THEN rt.id END) AS review_receipts
    FROM raw_receipts rr
    LEFT JOIN receipt_tables rt
      ON rt.raw_receipt_id = rr.id
     AND rt.household_id = :household_id
     AND rt.deleted_at IS NULL
    WHERE rr.household_id = :household_id
      AND rr.deleted_at IS NULL
      AND rr.duplicate_of_raw_receipt_id IS NULL
      AND rr.source_id IN (:ah_source, :lidl_source, :jumbo_source)
    GROUP BY rr.source_id
""")

_QUEUE_COUNTS_SQL = text("""
    SELECT provider, status, COUNT(*) AS item_count
    FROM retailer_import_queue
    WHERE household_id = :household_id
      AND provider IN ('lidl', 'jumbo')
    GROUP BY provider, status
""")


def load_retailer_history_progress(engine: Engine, *, household_id: str) -> dict:
    """Read counts only, never receipt data or credentials.

    Caller MUST resolve household_id via existing server-side session auth.
    Counts are observations, not a claim of complete retailer history.
    """
    owner = str(household_id or "").strip()
    if not owner:
        raise ValueError("Actief huishouden ontbreekt")

    with engine.connect() as conn:
        cutoff = read_household_cutover(conn, owner)
        params = {
            "household_id": owner,
            "cutover_enabled": int(cutoff is not None),
            "cutoff_datetime": datetime.combine(cutoff, time.min) if cutoff else None,
            **{f"{code}_source": f"{owner}-retailer-{code}" for code, _ in _PROVIDERS},
        }
        receipts = {
            str(row["source_id"]): dict(row)
            for row in conn.execute(_RECEIPT_COUNTS_SQL, params).mappings().all()
        }
        queue = {
            (str(row["provider"]), str(row["status"])): int(row["item_count"])
            for row in conn.execute(_QUEUE_COUNTS_SQL, {"household_id": owner}).mappings().all()
        }
        maintenance_state = conn.execute(text(
            "SELECT state FROM maintenance_control WHERE id = 1"
        )).scalar_one_or_none()
        enabled = is_platform_feature_enabled(conn, FEATURE_FLAG_RETAILER_AUTO_IMPORT)
        auto_import_paused = maintenance_state not in {"normal", "announced"} or not enabled

    providers = []
    for code, name in _PROVIDERS:
        row = receipts.get(f"{owner}-retailer-{code}", {})
        providers.append({
            "code": code,
            "name": name,
            "saved_receipts": int(row.get("saved_receipts") or 0),
            "kassa_receipts": int(row.get("kassa_receipts") or 0),
            # Null means no cutover, NOT "zero historical purchases".
            "historical_receipts": int(row.get("historical_receipts") or 0) if cutoff else None,
            "review_receipts": int(row.get("review_receipts") or 0) if cutoff else None,
            "queue_pending": queue.get((code, "pending"), 0),
            "queue_processing": queue.get((code, "processing"), 0),
            "queue_review_required": queue.get((code, "review_required"), 0),
            "queue_completed": queue.get((code, "completed"), 0),
        })
    return {
        "coverage": "persisted_retailer_receipts_and_queue_only",
        "history_cutover_enabled": cutoff is not None,
        "auto_import_paused": auto_import_paused,
        "complete_retailer_history_known": False,
        "providers": providers,
    }
