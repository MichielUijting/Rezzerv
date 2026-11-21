"""PR3 targeted fail-closed acceptance and identity/revision unit tests.

Run: PYTHONPATH=backend python -m unittest backend.tests.test_household_opening_stock_review_service
"""
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.household_opening_stock_review_service import (
    _review_item, confirm_opening_stock, proposal_revision,
    validate_opening_stock_quantity,
)


def proposal(**updates):
    value = {
        "key": "article:ha-1",
        "unit": "stuk",
        "household_article_id": "ha-1",
        "product_ids": [],
        "source_fingerprint": "a" * 64,
        "source_receipt_count": 4,
        "purchase_day_count": 4,
        "last_purchase_date": "2026-11-18",
        "estimated_opening_quantity": 1.2,
        "estimate_status": "indicative_unconfirmed",
    }
    value.update(updates)
    return value


class _QueryResult:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def first(self):
        return self.value

    def scalar(self):
        return self.value


class ReadConnection:
    def __init__(self, *, article=True, existing_stock=False, prior=None):
        self.article = article
        self.existing_stock = existing_stock
        self.prior = prior
        self.queries = []

    def execute(self, stmt, args=None):
        sql = str(stmt)
        self.queries.append((sql, args))
        assert sql.lstrip().upper().startswith("SELECT"), sql
        if "FROM household_articles" in sql:
            return _QueryResult("ha-1" if self.article else None)
        if "FROM household_opening_stock_confirmations" in sql:
            return _QueryResult(self.prior)
        if "FROM inventory_events" in sql:
            return _QueryResult(1 if self.existing_stock else None)
        if "FROM inventory" in sql:
            return _QueryResult(1 if self.existing_stock else None)
        raise AssertionError("Unexpected read: " + sql)


class OpeningStockReviewContractTests(unittest.TestCase):
    def test_quantity_never_truncates_decimal_or_accepts_bool(self):
        for value in (True, False, 0.5, 2.0, "2", None, -1, 10001):
            with self.subTest(value=value), self.assertRaises(HTTPException):
                validate_opening_stock_quantity(value)
        self.assertEqual(validate_opening_stock_quantity(0), 0)
        self.assertEqual(validate_opening_stock_quantity(10000), 10000)

    def test_exact_source_fingerprint_changes_revision(self):
        first = proposal_revision(proposal(), "2026-11-20")
        self.assertEqual(len(first), 64)
        self.assertNotEqual(first, proposal_revision(
            proposal(source_fingerprint="b" * 64), "2026-11-20",
        ))
        self.assertNotEqual(first, proposal_revision(proposal(), "2026-11-21"))
        self.assertNotEqual(first, proposal_revision(
            proposal(household_article_id="ha-2"), "2026-11-20",
        ))

    def test_get_is_read_only_and_blocks_uncertain_identities(self):
        for item in (
            proposal(key="product:gp-1"),
            proposal(key="confirmed_synonym:gp-1:gp-2"),
            proposal(household_article_id=None),
        ):
            conn = ReadConnection()
            output = _review_item(conn, household_id="house-1",
                                  cutoff="2026-11-20", item=item)
            self.assertEqual(output["review_status"], "identity_review_required")
            self.assertFalse(output["can_confirm"])
            self.assertFalse(conn.queries)

    def test_unit_and_household_article_guards(self):
        for args, reason in (
            ({"unit": "kg"}, "unit_review_required"),
            ({}, "article_unavailable"),
        ):
            conn = ReadConnection(article=reason != "article_unavailable")
            result = _review_item(
                conn, household_id="house-1", cutoff="2026-11-20",
                item=proposal(**args),
            )
            self.assertEqual(result["review_status"], reason)
            self.assertFalse(result["can_confirm"])

    def test_existing_stock_or_event_cannot_be_initialized_again(self):
        result = _review_item(
            ReadConnection(existing_stock=True),
            household_id="house-1", cutoff="2026-11-20", item=proposal(),
        )
        self.assertFalse(result["can_confirm"])
        self.assertEqual(result["review_status"], "existing_stock")

    def test_prior_confirmation_is_visible_but_not_writable(self):
        prior = {
            "confirmed_quantity": 3, "confirmed_at": "2026-11-21",
            "proposal_revision": "c" * 64,
        }
        result = _review_item(
            ReadConnection(prior=prior), household_id="house-1",
            cutoff="2026-11-20", item=proposal(),
        )
        self.assertEqual(result["review_status"], "confirmed")
        self.assertEqual(result["confirmed_quantity"], 3)
        self.assertFalse(result["can_confirm"])

    def test_explicit_confirmation_required_before_any_queries(self):
        conn = ReadConnection()
        args = dict(household_id="house-1", actor_user_id="actor-1",
                    proposal_key="article:ha-1",
                    proposal_revision_value="a" * 64,
                    household_article_id="ha-1", confirmed_quantity=1)
        with self.assertRaises(HTTPException):
            confirm_opening_stock(conn, **args, explicitly_confirmed=False)
        self.assertEqual(conn.queries, [])

    def test_foreign_household_article_and_invalid_identity_fail_closed(self):
        conn = ReadConnection(article=False)
        args = dict(household_id="house-2", actor_user_id="actor-2",
                    proposal_key="article:ha-1",
                    proposal_revision_value="a" * 64,
                    household_article_id="ha-1", confirmed_quantity=1,
                    explicitly_confirmed=True)
        with self.assertRaises(HTTPException) as raised:
            confirm_opening_stock(conn, **args)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(len(conn.queries), 1)
        self.assertEqual(conn.queries[0][1]["household_id"], "house-2")


if __name__ == "__main__":
    unittest.main()
