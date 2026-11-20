"""Fast, isolated contract for historical receipt inventory classification.

Run: python -m unittest backend.tests.test_receipt_historical_import_policy
"""
import unittest
from datetime import date, datetime

from fastapi import HTTPException
from app.services.receipt_historical_import_policy import (
    classify_purchase_date, require_batch_inventory_allowed,
)


class _Rows:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def mappings(self):
        return self

    def first(self):
        return self.value


class _FakeConnection:
    def __init__(self, *, cutover=None, batch=None, receipt=None):
        self.cutover = cutover
        self.batch = batch
        self.receipt = receipt
        self.queries = []

    def execute(self, statement, params=None):
        query = str(statement)
        self.queries.append((query, params))
        if "FROM household_receipt_history_cutovers" in query:
            return _Rows(self.cutover)
        if "FROM purchase_import_batches" in query:
            return _Rows(self.batch)
        if "FROM receipt_tables" in query:
            return _Rows(self.receipt)
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
