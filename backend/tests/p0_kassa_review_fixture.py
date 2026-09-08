"""Deterministic PostgreSQL fixture for the P0 Kassa browser review authority.

This script prepares only the state that exists before a user starts reviewing a
receipt. The review and approval mutations themselves must be performed through
the visible Kassa browser UI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import text

# The backend container executes this file from /app/tests. Keep /app itself on
# sys.path as well so imports made by the reused Kassa API authority can resolve
# the real ``app`` package.
APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from kassa_review_api_selftest import (
    SEED_PASSWORD,
    TARGET_ADMIN_EMAIL,
    TARGET_HOUSEHOLD,
    _prepare_database,
    _seed_receipt,
    create_postgresql_runtime_test_engine,
)

UNCERTAIN_KEY = "l4-review-uncertain"
FINANCIAL_KEY = "l4-review-financial"
UNCERTAIN_RECEIPT_ID = f"f3-kassa-receipt-{UNCERTAIN_KEY}"
FINANCIAL_RECEIPT_ID = f"f3-kassa-receipt-{FINANCIAL_KEY}"


def prepare() -> dict:
    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql", engine.dialect.name
        _prepare_database(engine)

        uncertain = _seed_receipt(
            engine,
            fixture_name="uncertain_match",
            seed_key=UNCERTAIN_KEY,
        )
        financial = _seed_receipt(
            engine,
            fixture_name="normal_physical",
            seed_key=FINANCIAL_KEY,
        )

        uncertain_product = str((uncertain["fixture"].get("selector") or {}).get("product_name") or "").strip()
        uncertain_line_id = str(uncertain["line_ids"][uncertain_product])

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE receipt_tables
                    SET store_name = 'L4 Onzekere Match'
                    WHERE id = :receipt_id
                    """
                ),
                {"receipt_id": UNCERTAIN_RECEIPT_ID},
            )
            conn.execute(
                text(
                    """
                    UPDATE receipt_tables
                    SET store_name = 'L4 Financiele Review',
                        total_amount = 999.99
                    WHERE id = :receipt_id
                    """
                ),
                {"receipt_id": FINANCIAL_RECEIPT_ID},
            )
            # The financial variant starts after ordinary line review. Seed that
            # precondition explicitly so its only remaining blocker is the
            # deliberately inconsistent receipt total.
            conn.execute(
                text(
                    """
                    UPDATE receipt_table_lines
                    SET is_validated = TRUE
                    WHERE receipt_table_id = :receipt_id
                    """
                ),
                {"receipt_id": FINANCIAL_RECEIPT_ID},
            )

            uncertain_state = conn.execute(
                text(
                    """
                    SELECT rtl.is_validated, rt.reviewed_at
                    FROM receipt_table_lines rtl
                    JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
                    WHERE rtl.id = :line_id
                    """
                ),
                {"line_id": uncertain_line_id},
            ).mappings().one()
            assert not bool(uncertain_state["is_validated"]), uncertain_state
            assert uncertain_state["reviewed_at"] is None, uncertain_state

            financial_state = conn.execute(
                text(
                    """
                    SELECT parse_status, totals_overridden, approved_at
                    FROM receipt_tables
                    WHERE id = :receipt_id
                    """
                ),
                {"receipt_id": FINANCIAL_RECEIPT_ID},
            ).mappings().one()
            assert str(financial_state["parse_status"]) == "review_needed", financial_state
            assert not bool(financial_state["totals_overridden"]), financial_state
            assert financial_state["approved_at"] is None, financial_state

            financial_unreviewed = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM receipt_table_lines
                    WHERE receipt_table_id = :receipt_id
                      AND COALESCE(is_deleted, FALSE) = FALSE
                      AND COALESCE(is_validated, FALSE) = FALSE
                    """
                ),
                {"receipt_id": FINANCIAL_RECEIPT_ID},
            ).scalar_one()
            assert int(financial_unreviewed or 0) == 0, financial_unreviewed

        return {
            "household_id": TARGET_HOUSEHOLD,
            "email": TARGET_ADMIN_EMAIL,
            "password": SEED_PASSWORD,
            "uncertain_receipt_id": UNCERTAIN_RECEIPT_ID,
            "uncertain_line_id": uncertain_line_id,
            "uncertain_product": uncertain_product,
            "financial_receipt_id": FINANCIAL_RECEIPT_ID,
        }
    finally:
        engine.dispose()


def verify() -> dict:
    engine = create_postgresql_runtime_test_engine()
    try:
        with engine.begin() as conn:
            uncertain = conn.execute(
                text(
                    """
                    SELECT rtl.is_validated, rtl.corrected_raw_label,
                           rt.reviewed_at, rt.parse_status, rt.approved_at,
                           rt.approved_by_user_email, rt.totals_overridden
                    FROM receipt_table_lines rtl
                    JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
                    WHERE rtl.id = :line_id
                    """
                ),
                {"line_id": f"f3-kassa-line-{UNCERTAIN_KEY}-1"},
            ).mappings().first()

            if uncertain is None:
                uncertain = conn.execute(
                    text(
                        """
                        SELECT rtl.is_validated, rtl.corrected_raw_label,
                               rt.reviewed_at, rt.parse_status, rt.approved_at,
                               rt.approved_by_user_email, rt.totals_overridden
                        FROM receipt_table_lines rtl
                        JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
                        WHERE rt.id = :receipt_id
                          AND rtl.article_match_status = 'uncertain'
                        ORDER BY rtl.line_index
                        LIMIT 1
                        """
                    ),
                    {"receipt_id": UNCERTAIN_RECEIPT_ID},
                ).mappings().one()

            assert bool(uncertain["is_validated"]), uncertain
            assert str(uncertain["corrected_raw_label"] or "").strip(), uncertain
            assert uncertain["reviewed_at"] is not None, uncertain
            assert str(uncertain["parse_status"]) == "approved", uncertain
            assert uncertain["approved_at"] is not None, uncertain
            assert str(uncertain["approved_by_user_email"] or "").lower() == TARGET_ADMIN_EMAIL.lower(), uncertain
            assert not bool(uncertain["totals_overridden"]), uncertain

            financial = conn.execute(
                text(
                    """
                    SELECT parse_status, approved_at, approved_by_user_email,
                           totals_overridden, totals_override_at, totals_override_by_user_email
                    FROM receipt_tables
                    WHERE id = :receipt_id
                    """
                ),
                {"receipt_id": FINANCIAL_RECEIPT_ID},
            ).mappings().one()
            assert str(financial["parse_status"]) == "approved_override", financial
            assert financial["approved_at"] is not None, financial
            assert str(financial["approved_by_user_email"] or "").lower() == TARGET_ADMIN_EMAIL.lower(), financial
            assert bool(financial["totals_overridden"]), financial
            assert financial["totals_override_at"] is not None, financial
            assert str(financial["totals_override_by_user_email"] or "").lower() == TARGET_ADMIN_EMAIL.lower(), financial

        return {"uncertain": dict(uncertain), "financial": dict(financial)}
    finally:
        engine.dispose()


def main() -> int:
    mode = str(sys.argv[1] if len(sys.argv) > 1 else "prepare").strip().lower()
    if mode == "prepare":
        payload = prepare()
        print("P0_KASSA_REVIEW_FIXTURE=" + json.dumps(payload, default=str, sort_keys=True))
        print("P0_KASSA_REVIEW_FIXTURE_GREEN")
        return 0
    if mode == "verify":
        payload = verify()
        print("P0_KASSA_REVIEW_POSTGRESQL_PROOF=" + json.dumps(payload, default=str, sort_keys=True))
        print("P0_KASSA_REVIEW_POSTGRESQL_GREEN")
        return 0
    raise SystemExit(f"Unsupported mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
