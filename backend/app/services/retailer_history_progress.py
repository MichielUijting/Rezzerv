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
from app.services.receipt_historical_import_policy import historical_history_start_date, read_household_cutover

_PROVIDERS = (("ah", "Albert Heijn"), ("lidl", "Lidl"), ("jumbo", "Jumbo"))

# Both sides of the join must be scoped to the *authorized* household.
# Receipt date must be the source's original, non-default date. A receipt
# created today but bought before the household cutover is historical.
_RECEIPT_COUNTS_SQL = text("""
    SELECT rr.source_id AS source_id,
           COUNT(DISTINCT rr.id) AS saved_receipts,
           COUNT(DISTINCT rt.id) AS kassa_receipts,
           COUNT(DISTINCT CASE
               WHEN rt.approved_at IS NULL
                AND (:cutover_enabled = 0
                     OR rt.purchase_at IS NULL
                     OR LOWER(TRIM(COALESCE(rt.purchase_at_source, ''))) = 'import_default'
                     OR CAST(rt.purchase_at AS DATE) >= :cutoff_date)
               THEN rt.id END) AS kassa_inbox_receipts,
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

_RECEIPT_EVIDENCE_SQL = text("""
    SELECT rt.purchase_at,
           rt.purchase_at_source,
           rt.created_at,
           rt.parse_status,
           rt.approved_at,
           (SELECT COUNT(*)
              FROM receipt_table_lines rtl
             WHERE rtl.receipt_table_id = rt.id
               AND COALESCE(rtl.is_deleted, FALSE) = FALSE) AS line_count
    FROM raw_receipts rr
    JOIN receipt_tables rt
      ON rt.raw_receipt_id = rr.id
     AND rt.household_id = :household_id
     AND rt.deleted_at IS NULL
    WHERE rr.household_id = :household_id
      AND rr.source_id = :source_id
      AND rr.deleted_at IS NULL
      AND rr.duplicate_of_raw_receipt_id IS NULL
    ORDER BY rt.created_at DESC, rt.id DESC
    LIMIT :limit
""")



# Historical LINE evidence is independent of the receipt-level parser status.
# A fully imported queue item does not prove any recognized or stocked items.
# These counts are deliberately distinct from the automatic stock baseline.
_HISTORICAL_LINE_COUNTS_SQL = text("""
    SELECT rr.source_id,
           COUNT(rtl.id) AS historical_line_count,
           COUNT(rtl.id) FILTER (
             WHERE rtl.line_role = 'product'
               AND COALESCE(rtl.inventory_eligible, FALSE) = TRUE
           ) AS physical_candidate_line_count,
           COUNT(rtl.id) FILTER (
             WHERE rtl.line_role = 'product'
               AND COALESCE(rtl.inventory_eligible, FALSE) = TRUE
               AND ha.id IS NOT NULL
           ) AS directly_linked_line_count,
           COUNT(rtl.id) FILTER (
             WHERE rtl.line_role = 'product'
               AND COALESCE(rtl.inventory_eligible, FALSE) = TRUE
               AND ha.id IS NULL
           ) AS unlinked_physical_line_count,
           COUNT(rtl.id) FILTER (
             WHERE rtl.line_role IS NULL
                OR rtl.line_role = 'unknown'
                OR (rtl.line_role = 'product'
                    AND COALESCE(rtl.inventory_eligible, FALSE) = FALSE)
           ) AS uncertain_line_count
    FROM raw_receipts rr
    JOIN receipt_tables rt
      ON rt.raw_receipt_id = rr.id
     AND rt.household_id = :household_id
     AND rt.deleted_at IS NULL
     AND COALESCE(rt.workflow_state, 'active') = 'active'
    JOIN receipt_table_lines rtl
      ON rtl.receipt_table_id = rt.id
     AND COALESCE(rtl.is_deleted, FALSE) = FALSE
    LEFT JOIN household_articles ha
      ON ha.id = rtl.matched_article_id
     AND ha.household_id = :household_id
     AND COALESCE(ha.status, 'active') = 'active'
    WHERE rr.household_id = :household_id
      AND rr.deleted_at IS NULL
      AND rr.duplicate_of_raw_receipt_id IS NULL
      AND rr.source_id IN (:ah_source, :lidl_source, :jumbo_source)
      AND rt.purchase_at IS NOT NULL
      AND LOWER(TRIM(COALESCE(rt.purchase_at_source, ''))) <> 'import_default'
      AND CAST(rt.purchase_at AS DATE) >= :history_start
      AND CAST(rt.purchase_at AS DATE) < :cutoff_date
    GROUP BY rr.source_id
""")

_HISTORICAL_OUTCOME_SQL = text("""
    SELECT
      (SELECT COUNT(*)
         FROM household_historical_auto_stock_baselines b
        WHERE b.household_id = :household_id) AS baseline_article_count,
      (SELECT COALESCE(SUM(b.quantity), 0)
         FROM household_historical_auto_stock_baselines b
        WHERE b.household_id = :household_id) AS baseline_unit_count,
      (SELECT COUNT(*)
         FROM household_historical_purchase_cadences c
        WHERE c.household_id = :household_id
          AND c.purchase_day_count >= 2) AS repurchase_cadence_article_count
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
            "cutoff_date": cutoff,
            "history_start": historical_history_start_date(cutoff) if cutoff else None,
            **{f"{code}_source": f"{owner}-retailer-{code}" for code, _ in _PROVIDERS},
        }
        receipts = {
            str(row["source_id"]): dict(row)
            for row in conn.execute(_RECEIPT_COUNTS_SQL, params).mappings().all()
        }
        historical_lines = ({
            str(row["source_id"]): dict(row)
            for row in conn.execute(_HISTORICAL_LINE_COUNTS_SQL, params).mappings().all()
        } if cutoff else {})
        historical_outcome = (dict(conn.execute(
            _HISTORICAL_OUTCOME_SQL, {"household_id": owner},
        ).mappings().first()) if cutoff else None)
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
        evidence = historical_lines.get(f"{owner}-retailer-{code}", {})
        providers.append({
            "code": code,
            "name": name,
            "saved_receipts": int(row.get("saved_receipts") or 0),
            "kassa_receipts": int(row.get("kassa_receipts") or 0),
            "kassa_inbox_receipts": int(row.get("kassa_inbox_receipts") or 0),
            # Null means no cutover, NOT "zero historical purchases".
            "historical_receipts": int(row.get("historical_receipts") or 0) if cutoff else None,
            "review_receipts": int(row.get("review_receipts") or 0) if cutoff else None,
            # Informational *line* evidence. Links alone do not prove that
            # a line passed all quantity/date/replay guards or was stocked.
            "historical_line_count": int(evidence.get("historical_line_count") or 0) if cutoff else None,
            "physical_candidate_line_count": int(evidence.get("physical_candidate_line_count") or 0) if cutoff else None,
            "directly_linked_line_count": int(evidence.get("directly_linked_line_count") or 0) if cutoff else None,
            "unlinked_physical_line_count": int(evidence.get("unlinked_physical_line_count") or 0) if cutoff else None,
            "uncertain_line_count": int(evidence.get("uncertain_line_count") or 0) if cutoff else None,
            "queue_pending": queue.get((code, "pending"), 0),
            "queue_processing": queue.get((code, "processing"), 0),
            "queue_review_required": queue.get((code, "review_required"), 0),
            "queue_completed": queue.get((code, "completed"), 0),
        })
    return {
        "coverage": "persisted_receipts_lines_queue_and_historical_baseline",
        "history_start_date": historical_history_start_date(cutoff).isoformat() if cutoff else None,
        "historical_stock": ({
            "baseline_article_count": int(historical_outcome.get("baseline_article_count") or 0),
            "baseline_unit_count": int(historical_outcome.get("baseline_unit_count") or 0),
            "repurchase_cadence_article_count": int(historical_outcome.get("repurchase_cadence_article_count") or 0),
        } if historical_outcome is not None else None),
        "history_cutover_enabled": cutoff is not None,
        "auto_import_paused": auto_import_paused,
        "complete_retailer_history_known": False,
        "providers": providers,
    }


def load_retailer_history_evidence(
    engine: Engine, *, household_id: str, provider: str, limit: int = 10,
) -> dict:
    """Show only minimal, read-only provenance for a household's saved receipts.

    Never return receipt contents, external references, raw IDs, loyalty data,
    OAuth credentials or data from a client-supplied household.
    """
    owner = str(household_id or "").strip()
    code = str(provider or "").strip().lower()
    if not owner:
        raise ValueError("Actief huishouden ontbreekt")
    if code not in {key for key, _ in _PROVIDERS}:
        raise ValueError("Winkel niet ondersteund")
    bounded = min(max(int(limit), 1), 10)
    source_id = f"{owner}-retailer-{code}"

    def date_part(value):
        return str(value)[:10] if value is not None else None

    with engine.connect() as conn:
        rows = conn.execute(
            _RECEIPT_EVIDENCE_SQL,
            {"household_id": owner, "source_id": source_id, "limit": bounded},
        ).mappings().all()
    return {
        "provider": code,
        "coverage": "most_recent_persisted_receipt_records_only",
        "items": [{
            "purchase_date": date_part(row.get("purchase_at")),
            "received_date": date_part(row.get("created_at")),
            "purchase_date_source": str(row.get("purchase_at_source") or ""),
            "parse_status": str(row.get("parse_status") or ""),
            "line_count": int(row.get("line_count") or 0),
            "approved": row.get("approved_at") is not None,
        } for row in rows],
    }
