"""Approved-receipt precondition for the P0 Uitpakken browser authority.

The visible Uitpakken overview is receipt-authoritative: only approved receipt
rows are eligible and their purchase-import batch is identified as a receipt
batch. This helper bridges the deterministic day-article batch prepared by
``p0_unpacking_fixture.py`` into that real production selection contract.
It does not process inventory and does not perform the browser mutation.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import text

from app.testing.postgresql_onboarding_selftest_fixture import create_postgresql_runtime_test_engine

HOUSEHOLD_ID = "p0-unpacking-household"
ADMIN_EMAIL = "p0-unpacking-admin@rezzerv.local"
ARTICLE_ID = "canonical-day-bananas"
ARTICLE_NAME = "Bananen"
BATCH_ID = "p0-unpacking-day-article-batch"
LINE_ID = "p0-unpacking-day-article-line"
RECEIPT_ID = "p0-unpacking-day-article-receipt"
RAW_RECEIPT_ID = "p0-unpacking-day-article-raw"
RECEIPT_LINE_ID = "p0-unpacking-day-article-receipt-line"
SOURCE_REFERENCE = f"receipt:{RECEIPT_ID}"
EXTERNAL_LINE_REF = f"receipt-line:{RECEIPT_LINE_ID}"


def prepare() -> dict:
    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql", engine.dialect.name
        with engine.begin() as conn:
            current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
            runtime_create = bool(
                conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()
            )
            assert current_user == "rezzerv_app", current_user
            assert runtime_create is False

            # Repeatable fixture cleanup is scoped to the dedicated P0 receipt.
            conn.execute(
                text("DELETE FROM receipt_table_lines WHERE receipt_table_id = :receipt_id"),
                {"receipt_id": RECEIPT_ID},
            )
            conn.execute(
                text("DELETE FROM receipt_tables WHERE id = :receipt_id"),
                {"receipt_id": RECEIPT_ID},
            )
            conn.execute(
                text("DELETE FROM raw_receipts WHERE id = :raw_receipt_id"),
                {"raw_receipt_id": RAW_RECEIPT_ID},
            )

            sha256_hash = hashlib.sha256(b"p0-unpacking:canonical-day-bananas").hexdigest()
            conn.execute(
                text(
                    """
                    INSERT INTO raw_receipts (
                        id, household_id, source_id, original_filename, mime_type,
                        storage_path, sha256_hash, raw_status
                    ) VALUES (
                        :id, :household_id, NULL, 'p0-unpacking-bananen.pdf', 'application/pdf',
                        '/tmp/p0-unpacking-bananen.pdf', :sha256_hash, 'parsed'
                    )
                    """
                ),
                {
                    "id": RAW_RECEIPT_ID,
                    "household_id": HOUSEHOLD_ID,
                    "sha256_hash": sha256_hash,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO receipt_tables (
                        id, raw_receipt_id, household_id, store_name, store_branch,
                        purchase_at, total_amount, discount_total, currency, parse_status,
                        confidence_score, line_count, logical_receipt_key, workflow_state,
                        reviewed_at, approved_at, approved_by_user_email, totals_overridden
                    ) VALUES (
                        :id, :raw_receipt_id, :household_id, 'P0 Uitpakken testwinkel', NULL,
                        '2026-09-08T12:00:00', 1.00, 0, 'EUR', 'approved',
                        0.99, 1, 'p0-unpacking:canonical-day-bananas', 'active',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :approved_by, FALSE
                    )
                    """
                ),
                {
                    "id": RECEIPT_ID,
                    "raw_receipt_id": RAW_RECEIPT_ID,
                    "household_id": HOUSEHOLD_ID,
                    "approved_by": ADMIN_EMAIL,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO receipt_table_lines (
                        id, receipt_table_id, line_index, raw_label, normalized_label,
                        quantity, unit, unit_price, line_total, discount_amount,
                        article_match_status, matched_article_id, confidence_score,
                        logical_line_key, is_validated, line_role, inventory_eligible
                    ) VALUES (
                        :id, :receipt_id, 1, :article_name, 'bananen',
                        2, 'stuks', 0.50, 1.00, 0,
                        'matched', NULL, 0.99,
                        'p0-unpacking:canonical-day-bananas:1', TRUE, 'product', 1
                    )
                    """
                ),
                {
                    "id": RECEIPT_LINE_ID,
                    "receipt_id": RECEIPT_ID,
                    "article_name": ARTICLE_NAME,
                },
            )

            # Make the already deterministic purchase batch discoverable through
            # the exact approved-receipt identity used by /api/unpack-start-batches.
            batch_update = conn.execute(
                text(
                    """
                    UPDATE purchase_import_batches
                    SET source_type = 'receipt',
                        source_reference = :source_reference,
                        raw_payload = :raw_payload
                    WHERE id = :batch_id
                      AND household_id = :household_id
                    """
                ),
                {
                    "batch_id": BATCH_ID,
                    "household_id": HOUSEHOLD_ID,
                    "source_reference": SOURCE_REFERENCE,
                    "raw_payload": json.dumps({
                        "fixture": "canonical-day-article",
                        "receipt_table_id": RECEIPT_ID,
                        "store_name": "P0 Uitpakken testwinkel",
                        "purchase_date": "2026-09-08",
                    }),
                },
            )
            assert int(batch_update.rowcount or 0) == 1, batch_update.rowcount

            # sync_unpack_batch_lines_for_receipt keys existing lines by the
            # receipt-line reference. Manual identity/location overrides preserve
            # the canonical household article and Direct destination while the
            # production receipt sync refreshes receipt-owned fields.
            line_update = conn.execute(
                text(
                    """
                    UPDATE purchase_import_lines
                    SET external_line_ref = :external_line_ref,
                        match_status = 'matched',
                        review_decision = 'selected',
                        matched_household_article_id = :article_id,
                        suggested_household_article_id = :article_id,
                        article_override_mode = 'manual',
                        location_override_mode = 'manual',
                        is_auto_prefilled = FALSE,
                        processing_status = 'pending',
                        processed_at = NULL,
                        processed_event_id = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :line_id
                      AND batch_id = :batch_id
                    """
                ),
                {
                    "external_line_ref": EXTERNAL_LINE_REF,
                    "article_id": ARTICLE_ID,
                    "line_id": LINE_ID,
                    "batch_id": BATCH_ID,
                },
            )
            assert int(line_update.rowcount or 0) == 1, line_update.rowcount

            eligible = conn.execute(
                text(
                    """
                    SELECT rt.id, rt.approved_at, rt.parse_status,
                           pib.id AS batch_id, pib.source_type, pib.source_reference,
                           pil.id AS line_id, pil.external_line_ref,
                           pil.matched_household_article_id, pil.target_location_id
                    FROM receipt_tables rt
                    JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                    JOIN purchase_import_batches pib
                      ON pib.household_id = rt.household_id
                     AND pib.source_type = 'receipt'
                     AND pib.source_reference = :source_reference
                    JOIN purchase_import_lines pil ON pil.batch_id = pib.id
                    WHERE rt.id = :receipt_id
                      AND rt.household_id = :household_id
                      AND rt.approved_at IS NOT NULL
                      AND lower(trim(COALESCE(rt.parse_status, ''))) IN ('approved', 'approved_override')
                      AND pil.id = :line_id
                    """
                ),
                {
                    "source_reference": SOURCE_REFERENCE,
                    "receipt_id": RECEIPT_ID,
                    "household_id": HOUSEHOLD_ID,
                    "line_id": LINE_ID,
                },
            ).mappings().one()
            assert str(eligible["batch_id"]) == BATCH_ID, eligible
            assert str(eligible["line_id"]) == LINE_ID, eligible
            assert str(eligible["external_line_ref"]) == EXTERNAL_LINE_REF, eligible
            assert str(eligible["matched_household_article_id"]) == ARTICLE_ID, eligible
            assert str(eligible["target_location_id"] or "").strip(), eligible

        payload = {
            "receipt_id": RECEIPT_ID,
            "receipt_line_id": RECEIPT_LINE_ID,
            "batch_id": BATCH_ID,
            "line_id": LINE_ID,
            "source_reference": SOURCE_REFERENCE,
        }
        print("P0_UNPACKING_RECEIPT_BRIDGE=" + json.dumps(payload, sort_keys=True))
        print("P0_UNPACKING_RECEIPT_BRIDGE_GREEN")
        return payload
    finally:
        engine.dispose()


if __name__ == "__main__":
    prepare()
