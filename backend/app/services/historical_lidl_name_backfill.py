"""Conservative historical Lidl display-name correction for existing digital receipts.

Only the *derived* corrected_raw_label may be filled, and only when it has
never been set. Original line text, pricing, quantity, VAT, user corrections,
article identity and inventory are immutable here. The caller runs inside the
existing household-cutover transaction before replay and cadence calculation.
"""
from __future__ import annotations

from sqlalchemy import text

from app.integrations.retailer_receipts.normalizer import clean_lidl_transaction_label


def normalize_stored_lidl_purchase_names(conn, *, household_id: str, rows) -> int:
    """Apply proven transaction-tail parsing to stored historical Lidl lines.

    Rows come from the trusted, household-filtered historical receipt query.
    The guarded SQL checks that authority again when updating, preventing
    cross-household writes and stale source reuse. A second run writes zero.
    """
    owner = str(household_id or "").strip()
    if not owner or owner == "0":
        raise ValueError("Historisch Lidl-herstel vereist een regulier huishouden")
    changed = 0
    for record in rows:
        row = dict(record)
        if row.get("source_type") != "retailer_api" or row.get("source_provider") != "lidl":
            continue
        # A stored correction might be the user's deliberate choice. Even
        # when it equals the raw text, we cannot infer its provenance.
        if row.get("corrected_raw_label") is not None:
            continue
        original = str(row.get("raw_label") or "")
        normalized, _, _, _ = clean_lidl_transaction_label(original)
        if not normalized or normalized == " ".join(original.split()):
            continue
        line_id = str(row.get("line_id") or "").strip()
        receipt_id = str(row.get("receipt_table_id") or "").strip()
        if not line_id or not receipt_id:
            raise ValueError("Historische Lidl-regel mist herleidbare bronidentiteit")
        result = conn.execute(text("""
            UPDATE receipt_table_lines AS rtl
            SET corrected_raw_label = :normalized_name
            WHERE rtl.id = :line_id AND rtl.receipt_table_id = :receipt_id
              AND rtl.raw_label = :raw_label
              AND rtl.corrected_raw_label IS NULL
              AND COALESCE(rtl.is_deleted, FALSE) = FALSE
              AND EXISTS (
                  SELECT 1
                  FROM receipt_tables rt
                  JOIN raw_receipts rr
                    ON rr.id = rt.raw_receipt_id AND rr.household_id = rt.household_id
                  JOIN receipt_sources rs
                    ON rs.id = rr.source_id AND rs.household_id = rt.household_id
                  JOIN household_receipt_history_cutovers hrc
                    ON hrc.household_id = rt.household_id
                  WHERE rt.id = :receipt_id AND rt.household_id = :household_id
                    AND rs.type = 'retailer_api' AND rs.source_path = 'lidl'
                    AND rt.deleted_at IS NULL AND rr.deleted_at IS NULL
                    AND rr.duplicate_of_raw_receipt_id IS NULL
                    AND COALESCE(rt.workflow_state, 'active') = 'active'
                    AND rt.purchase_at IS NOT NULL
                    AND LOWER(TRIM(COALESCE(rt.purchase_at_source, ''))) <> 'import_default'
                    AND CAST(rt.purchase_at AS DATE) < hrc.first_current_purchase_date
              )
        """), {
            "household_id": owner,
            "line_id": line_id,
            "receipt_id": receipt_id,
            "raw_label": original,
            "normalized_name": normalized,
        })
        count = int(result.rowcount or 0)
        if count not in (0, 1):
            raise ValueError("Historisch Lidl-herstel raakt meerdere bronregels")
        changed += count
    return changed
