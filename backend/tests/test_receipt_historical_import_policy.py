"""Fast, isolated contract for historical receipt inventory classification.

Run: python -m unittest backend.tests.test_receipt_historical_import_policy
"""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

# Allow a targeted run from the repository root without global PYTHONPATH changes.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import HTTPException
from app.services.receipt_historical_import_policy import (
    classify_purchase_date, require_batch_inventory_allowed,
)


class _Rows:
    def __init__(self, value, rowcount=0):
        self.value = value
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self.value

    def mappings(self):
        return self

    def first(self):
        return self.value


class _FakeConnection:
    def __init__(self, *, cutover=None, batch=None, receipt=None,
                 existing_table=None):
        self.cutover = cutover
        self.batch = batch
        self.receipt = receipt
        self.existing_table = existing_table
        self.queries = []

    def execute(self, statement, params=None):
        query = str(statement)
        self.queries.append((query, params))
        if "FROM household_receipt_history_cutovers" in query:
            return _Rows(self.cutover)
        if "FROM purchase_import_batches" in query:
            if "SELECT 1" in query:
                return _Rows(
                    1 if self.existing_table == "purchase_import_batches" else None
                )
            return _Rows(self.batch)
        if "FROM receipt_tables" in query:
            if "SELECT 1" in query:
                return _Rows(1 if self.existing_table == "receipt_tables" else None)
            return _Rows(self.receipt)
        for table in ("raw_receipts", "purchase_import_batches",
                      "inventory_events", "inventory"):
            if f"FROM {table}" in query and "SELECT 1" in query:
                return _Rows(1 if self.existing_table == table else None)
        if "INSERT INTO household_receipt_history_cutovers" in query:
            return _Rows(None, rowcount=1)
        raise AssertionError("Unexpected query")


class ReceiptHistoricalImportPolicyTest(unittest.TestCase):
    def test_no_activation_preserves_legacy(self):
        self.assertEqual(
            classify_purchase_date("2020-01-01", purchase_at_source=None,
                                   first_current_purchase_date=None), "legacy",
        )

    def test_old_receipt_is_historical_even_when_imported_later(self):
        self.assertEqual(
            classify_purchase_date(datetime(2026, 10, 30, 15, 0),
                purchase_at_source="retailer", first_current_purchase_date=date(2026, 11, 20)),
            "historical",
        )

    def test_cutover_day_and_later_are_current(self):
        for purchase in ("2026-11-20T08:00:00", "2026-11-21"):
            with self.subTest(purchase=purchase):
                self.assertEqual(classify_purchase_date(
                    purchase, purchase_at_source="retailer",
                    first_current_purchase_date="2026-11-20"), "current")

    def test_missing_or_import_default_timestamp_is_not_stock_evidence(self):
        for purchase, source in ((None, "retailer"), ("invalid", "retailer"),
                                 ("2026-11-20", "import_default")):
            with self.subTest(purchase=purchase, source=source):
                self.assertEqual(classify_purchase_date(
                    purchase, purchase_at_source=source,
                    first_current_purchase_date="2026-11-20"), "review_required")

    def test_old_receipt_batch_is_blocked_before_stock_write(self):
        conn = _FakeConnection(
            cutover=date(2026, 11, 20),
            batch={"source_type": "receipt", "source_reference": "receipt:receipt-1"},
            receipt={"purchase_at": datetime(2026, 11, 1),
                     "purchase_at_source": "retailer"},
        )
        with self.assertRaises(HTTPException) as raised:
            require_batch_inventory_allowed(conn, household_id="home-1", batch_id="batch-1")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertTrue(all(params.get("household_id") == "home-1"
                            for query, params in conn.queries
                            if "FROM receipt_tables" in query or
                               "FROM household_receipt_history_cutovers" in query or
                               "FROM purchase_import_batches" in query))

    def test_date_missing_blocks_with_cutover(self):
        conn = _FakeConnection(cutover=date(2026, 11, 20),
            batch={"source_type": "receipt", "source_reference": "receipt:receipt-2"},
            receipt={"purchase_at": None, "purchase_at_source": "retailer"})
        with self.assertRaises(HTTPException):
            require_batch_inventory_allowed(conn, household_id="home-1", batch_id="batch-2")

    def test_cross_household_receipt_reference_fails_closed(self):
        # The receipt query must not accept an id from another household.
        conn = _FakeConnection(
            cutover=date(2026, 11, 20),
            batch={"source_type": "receipt", "source_reference": "receipt:foreign-id"},
            receipt=None,
        )
        with self.assertRaises(HTTPException) as raised:
            require_batch_inventory_allowed(conn, household_id="home-1", batch_id="batch-1")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertTrue(any("household_id = :household_id" in query
                            for query, _ in conn.queries
                            if "FROM receipt_tables" in query))

    def test_activate_only_on_empty_new_household(self):
        from app.services.receipt_historical_import_policy import (
            activate_cutover_for_new_onboarding,
        )
        conn = _FakeConnection(cutover=None)
        self.assertTrue(activate_cutover_for_new_onboarding(
            conn, household_id="new-home"))
        self.assertTrue(any(
            "INSERT INTO household_receipt_history_cutovers" in sql
            for sql, _ in conn.queries
        ))
        for table in ("raw_receipts", "receipt_tables",
                      "purchase_import_batches", "inventory_events", "inventory"):
            self.assertTrue(any("FROM " + table in sql for sql, _ in conn.queries))
        self.assertTrue(all(params["household_id"] == "new-home"
            for _, params in conn.queries))

    def test_no_activation_with_existing_receipts_or_inventory(self):
        from app.services.receipt_historical_import_policy import (
            activate_cutover_for_new_onboarding,
        )
        for table in ("raw_receipts", "receipt_tables",
                      "purchase_import_batches", "inventory_events", "inventory"):
            conn = _FakeConnection(cutover=None, existing_table=table)
            self.assertFalse(activate_cutover_for_new_onboarding(
                conn, household_id="existing-home"))
            self.assertFalse(any(
                "INSERT INTO household_receipt_history_cutovers" in sql
                for sql, _ in conn.queries
            ))

    def test_without_cutover_old_receipt_is_not_reclassified(self):
        conn = _FakeConnection(cutover=None,
            batch={"source_type": "receipt", "source_reference": "receipt:receipt-1"})
        require_batch_inventory_allowed(conn, household_id="legacy-home", batch_id="batch")

    def test_new_receipt_and_nonreceipt_batches_pass(self):
        conn = _FakeConnection(cutover=date(2026, 11, 20),
            batch={"source_type": "receipt", "source_reference": "receipt:receipt-3"},
            receipt={"purchase_at": date(2026, 11, 21), "purchase_at_source": "retailer"})
        require_batch_inventory_allowed(conn, household_id="home-1", batch_id="batch-3")
        other = _FakeConnection(cutover=date(2026, 11, 20),
            batch={"source_type": "manual", "source_reference": "manual:1"})
        require_batch_inventory_allowed(other, household_id="home-1", batch_id="manual")
        self.assertFalse(any("household_receipt_history_cutovers" in query for query, _ in other.queries))


if __name__ == "__main__":
    unittest.main()
