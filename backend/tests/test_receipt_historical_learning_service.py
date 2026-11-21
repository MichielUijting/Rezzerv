"""Targeted PR2 tests: historical learning never becomes physical stock.

Run: PYTHONPATH=backend python -m unittest backend.tests.test_receipt_historical_learning_service
"""
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.receipt_historical_learning_service import (
    MAX_SOURCE_ROWS, load_historical_learning, project_historical_learning,
)


CUTOFF = date(2026, 11, 20)


def row(day, *, receipt=None, product="gp-1", quantity=1, unit="stuk", **changes):
    rid = receipt or str(day)
    value = {
        "receipt_table_id": rid,
        "line_id": rid + "-item",
        "purchase_at": day,
        "purchase_at_source": "retailer",
        "sha256_hash": "hash-" + rid,
        "line_type": "product",
        "line_role": "product",
        "inventory_eligible": True,
        "article_match_status": "product_matched",
        "matched_article_id": None,
        "matched_global_product_id": product,
        "quantity": quantity,
        "unit": unit,
        "product_id": product,
        "product_name": "Koffie",
        "product_status": "active",
        "variant": "",
        "size_value": None,
        "size_unit": None,
        "explicit_household_article_id": None,
        "article_product_id": None,
        "household_article_name": None,
        "article_status": None,
    }
    value.update(changes)
    return value


def recurrent():
    return [
        row(date(2026, 8, 28), receipt="1"),
        row(date(2026, 9, 27), receipt="2"),
        row(date(2026, 10, 27), receipt="3"),
        row(date(2026, 11, 18), receipt="4"),
    ]


class Rows:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def mappings(self):
        return self

    def all(self):
        return self.value


class ReadOnlyConnection:
    def __init__(self, cutoff, rows=None):
        self.cutoff = cutoff
        self.rows = rows or []
        self.queries = []

    def execute(self, stmt, args=None):
        sql = str(stmt)
        self.queries.append((sql, args))
        if "FROM household_receipt_history_cutovers" in sql:
            return Rows(self.cutoff)
        if "FROM receipt_tables rt" in sql:
            return Rows(self.rows)
        raise AssertionError("Unexpected read, especially a write: " + sql)


class HistoricalBuyingLearningTest(unittest.TestCase):
    def test_trusted_history_yields_only_unconfirmed_estimate(self):
        result = project_historical_learning(recurrent(), cutoff=CUTOFF)
        self.assertEqual(result["status"], "analysis_only")
        self.assertFalse(result["writes_inventory"])
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["total"], 1)
        item = result["items"][0]
        self.assertEqual(item["estimate_status"], "indicative_unconfirmed")
        self.assertEqual(item["purchase_day_count"], 4)
        self.assertEqual(item["source_receipt_count"], 4)
        self.assertGreater(item["estimated_opening_quantity"], 0)
        self.assertLess(item["estimated_opening_quantity"], 1)
        self.assertEqual(item["product_ids"], ["gp-1"])

    def test_duplicate_raw_receipt_sha_not_double_counted(self):
        data = recurrent()
        duplicate = row(date(2026, 10, 27), receipt="copied",
                        sha256_hash="hash-3", quantity=10)
        result = project_historical_learning(data + [duplicate], cutoff=CUTOFF)
        self.assertEqual(result["items"][0]["source_receipt_count"], 4)
        self.assertEqual(result["excluded_rows"], 1)

    def test_financial_unknown_and_deleted_match_are_not_stock_evidence(self):
        original = recurrent()
        invalid = [
            row(date(2026, 11, 15), receipt="financial", line_role="financial", inventory_eligible=False),
            row(date(2026, 11, 16), receipt="unknown", line_role=None, line_type="unknown",
                inventory_eligible=None),
            row(date(2026, 11, 17), receipt="unmatched", article_match_status="unmatched"),
            row(date(2026, 11, 17), receipt="dangling", matched_article_id="foreign",
                explicit_household_article_id=None),
            row(date(2026, 11, 17), receipt="conflict", matched_article_id="ha1",
                explicit_household_article_id="ha1", article_product_id="other-gp"),
            row(date(2026, 11, 17), receipt="bad-date", purchase_at_source="import_default"),
            row(date(2026, 11, 17), receipt="bad-quantity", quantity=-3),
            row(CUTOFF, receipt="current"),
        ]
        result = project_historical_learning(original + invalid, cutoff=CUTOFF)
        self.assertEqual(result["excluded_rows"], len(invalid))
        self.assertEqual(result["items"][0]["source_receipt_count"], 4)

    def test_household_article_without_central_product_stays_its_own_identity(self):
        base = row(date(2026, 11, 1), product=None, receipt="explicit",
                   matched_article_id="ha1", explicit_household_article_id="ha1",
                   household_article_name="Handmatig bepaald")
        result = project_historical_learning([base], cutoff=CUTOFF)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["key"], "article:ha1")
        self.assertIsNone(result["items"][0]["estimated_opening_quantity"])
        self.assertEqual(result["items"][0]["household_article_id"], "ha1")

    def test_insufficient_observations_cannot_create_estimate(self):
        sample = [row(date(2026, 11, 1), receipt="one")]
        res = project_historical_learning(sample, cutoff=CUTOFF)["items"][0]
        self.assertEqual(res["reason"], "too_few_purchase_days")
        self.assertIsNone(res["estimated_opening_quantity"])

        recent = [row(date(2026, 11, 1) + timedelta(days=i * 2), receipt=str(i))
                  for i in range(4)]
        res = project_historical_learning(recent, cutoff=CUTOFF)["items"][0]
        self.assertEqual(res["reason"], "short_observation_period")

    def test_mixed_units_never_claim_quantity(self):
        samples = recurrent()
        samples[0]["unit"] = "kg"
        result = project_historical_learning(samples, cutoff=CUTOFF)
        self.assertEqual(result["total"], 2)
        self.assertTrue(all(it["reason"] == "incompatible_units" for it in result["items"]))
        self.assertTrue(all(it["estimated_opening_quantity"] is None for it in result["items"]))

    def test_synonym_aggregation_requires_explicit_confirmed_factors(self):
        rows = [
            row(date(2026, 9, 1), receipt="a", product="p1", quantity=2),
            row(date(2026, 10, 1), receipt="b", product="p2", quantity=1),
            row(date(2026, 11, 1), receipt="c", product="p1", quantity=2),
        ]
        no_evidence = project_historical_learning(rows, cutoff=CUTOFF)
        self.assertEqual(no_evidence["total"], 2)
        approved = {"p1": (("confirmed_synonym", "p1:p2", "Bevestigde synoniemen", "l"), 0.5),
                    "p2": (("confirmed_synonym", "p1:p2", "Bevestigde synoniemen", "l"), 1.0)}
        result = project_historical_learning(rows, cutoff=CUTOFF, synonym_factors=approved)
        self.assertEqual(result["total"], 1)
        item = result["items"][0]
        self.assertEqual(item["unit"], "l")
        self.assertEqual(item["product_ids"], ["p1", "p2"])
        self.assertEqual(item["estimate_status"], "indicative_unconfirmed")

    def test_legacy_household_and_source_limit_fail_closed(self):
        self.assertEqual(project_historical_learning(recurrent(), cutoff=None)["total"], 0)
        limit = [row(date(2026, 10, 1), receipt=str(i)) for i in range(MAX_SOURCE_ROWS + 1)]
        result = project_historical_learning(limit, cutoff=CUTOFF)
        self.assertEqual(result["status"], "source_limit_reached")
        self.assertEqual(result["items"], [])

    def test_real_loader_is_read_only_and_scoped(self):
        connection = ReadOnlyConnection(CUTOFF, recurrent())
        result = load_historical_learning(connection, household_id="home-1",
                                          page=1, page_size=10)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["page"], 1)
        self.assertEqual(len(connection.queries), 2)
        for sql, params in connection.queries:
            self.assertTrue(sql.lstrip().upper().startswith("SELECT"))
            self.assertEqual(params["household_id"], "home-1")
        query = connection.queries[1][0]
        self.assertIn("rt.deleted_at IS NULL", query)
        self.assertIn("rr.deleted_at IS NULL", query)
        self.assertIn("rt.approved_at IS NOT NULL", query)
        self.assertIn("first_current_purchase_date", query)
        self.assertIn("ha.household_id = rt.household_id", query)

    def test_no_cutover_performs_no_historical_query(self):
        connection = ReadOnlyConnection(None, recurrent())
        result = load_historical_learning(connection, household_id="legacy")
        self.assertEqual(result["status"], "legacy_not_enabled")
        self.assertEqual(len(connection.queries), 1)

    def test_bad_owner_does_not_read(self):
        connection = ReadOnlyConnection(CUTOFF)
        for owner in ("", "0"):
            with self.subTest(owner=owner), self.assertRaises(ValueError):
                load_historical_learning(connection, household_id=owner)
        self.assertEqual(connection.queries, [])


if __name__ == "__main__":
    unittest.main()
