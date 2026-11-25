"""Deterministic DML contract for first-store onboarding.

No test database is constructed here. A minimal connection double checks every
query's household predicate; real PostgreSQL behavior belongs to the required
full-stack authority and browser onboarding journey.
"""
from __future__ import annotations

import unittest

from app.services.store_onboarding_progress_service import (
    read_store_onboarding, record_store_result, seed_store_onboarding,
    update_store_selection,
)


class _Result:
    def __init__(self, value=None, rowcount=0):
        self.value = value
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self.value


class HouseholdBoundConnection:
    """In-process DML contract; fail on unexpected SQL or missing owner."""

    def __init__(self):
        self.settings = {}
        self.credentials = set()
        self.queues = set()

    def execute(self, statement, params):
        sql = " ".join(str(statement).split()).upper()
        owner = params.get("household_id")
        assert isinstance(owner, str) and owner, "Missing active owner on write/read"

        if sql.startswith("SELECT SETTING_VALUE FROM HOUSEHOLD_SETTINGS"):
            assert "HOUSEHOLD_ID = :HOUSEHOLD_ID" in sql
            assert "SETTING_KEY = :SETTING_KEY" in sql
            return _Result(self.settings.get((owner, params["setting_key"])))
        if sql.startswith("INSERT INTO HOUSEHOLD_SETTINGS"):
            assert "ON CONFLICT (HOUSEHOLD_ID, SETTING_KEY) DO NOTHING" in sql
            key = (owner, params["setting_key"])
            if key not in self.settings:
                self.settings[key] = params["setting_value"]
                return _Result(rowcount=1)
            return _Result(rowcount=0)
        if sql.startswith("UPDATE HOUSEHOLD_SETTINGS"):
            assert "WHERE HOUSEHOLD_ID = :HOUSEHOLD_ID AND SETTING_KEY = :SETTING_KEY" in sql
            key = (owner, params["setting_key"])
            if key not in self.settings:
                return _Result(rowcount=0)
            self.settings[key] = params["setting_value"]
            return _Result(rowcount=1)
        if "FROM RETAILER_ACCOUNT_CREDENTIALS" in sql:
            assert "WHERE HOUSEHOLD_ID = :HOUSEHOLD_ID AND PROVIDER = 'AH'" in sql
            return _Result(1 if (owner, "ah") in self.credentials else None)
        if "FROM RETAILER_IMPORT_QUEUE" in sql:
            assert "WHERE HOUSEHOLD_ID = :HOUSEHOLD_ID AND PROVIDER = :PROVIDER" in sql
            assert "AND ID = :QUEUE_ID" in sql
            return _Result(1 if (owner, params["provider"], params["queue_id"]) in self.queues else None)
        raise AssertionError(f"Unexpected DB operation in onboarding: {sql}")


class StoreOnboardingProgressTests(unittest.TestCase):
    def setUp(self):
        self.conn = HouseholdBoundConnection()
        seed_store_onboarding(self.conn, "first")
        seed_store_onboarding(self.conn, "second")

    def test_only_new_households_have_the_state(self):
        self.assertEqual(read_store_onboarding(self.conn, "legacy"), {
            "available": False, "selected": [], "results": {},
        })
        self.assertEqual(read_store_onboarding(self.conn, "first")["selected"], [])

    def test_seed_is_idempotent_and_does_not_reset(self):
        update_store_selection(self.conn, "first", ["ah", "jumbo"])
        seed_store_onboarding(self.conn, "first")
        self.assertEqual(read_store_onboarding(self.conn, "first")["selected"], ["ah", "jumbo"])

    def test_selection_multiple_order_stable_and_isolated(self):
        update_store_selection(self.conn, "first", ["lidl", "ah"])
        self.assertEqual(read_store_onboarding(self.conn, "first")["selected"], ["ah", "lidl"])
        self.assertEqual(read_store_onboarding(self.conn, "second")["selected"], [])

    def test_unseeded_household_cannot_write(self):
        with self.assertRaisesRegex(ValueError, "niet actief"):
            update_store_selection(self.conn, "legacy", ["ah"])

    def test_duplicate_and_unsupported_choice_denied(self):
        for selected in (["ah", "ah"], ["aldi"], ["jumbo", "plus"]):
            with self.assertRaises(ValueError):
                update_store_selection(self.conn, "first", selected)

    def test_failed_result_persists_without_proof(self):
        update_store_selection(self.conn, "first", ["lidl"])
        record_store_result(self.conn, "first", provider="lidl", result="failed")
        self.assertEqual(read_store_onboarding(self.conn, "first")["results"], {"lidl": "failed"})

    def test_ah_requires_own_credential_and_cannot_be_demoted(self):
        update_store_selection(self.conn, "first", ["ah"])
        self.conn.credentials.add(("second", "ah"))
        with self.assertRaisesRegex(ValueError, "niet door Inhuis bevestigd"):
            record_store_result(self.conn, "first", provider="ah", result="success")
        self.conn.credentials.add(("first", "ah"))
        state = record_store_result(self.conn, "first", provider="ah", result="success")
        self.assertEqual(state["results"]["ah"], "success")
        with self.assertRaises(ValueError):
            update_store_selection(self.conn, "first", [])
        self.assertEqual(
            record_store_result(self.conn, "first", provider="ah", result="failed")["results"]["ah"],
            "success",
        )

    def test_browser_success_requires_own_queued_receipt(self):
        update_store_selection(self.conn, "first", ["jumbo", "lidl"])
        self.conn.queues.update({
            ("second", "jumbo", "other-house"),
            ("first", "lidl", "wrong-provider"),
            ("first", "jumbo", "valid-jumbo"),
        })
        for queue_id in (None, "other-house", "wrong-provider"):
            with self.assertRaises(ValueError):
                record_store_result(self.conn, "first", provider="jumbo",
                                    result="success", queue_id=queue_id)
        result = record_store_result(self.conn, "first", provider="jumbo",
                                     result="success", queue_id="valid-jumbo")
        self.assertEqual(result["results"], {"jumbo": "success"})
        self.assertEqual(read_store_onboarding(self.conn, "second")["results"], {})

    def test_no_result_for_unselected_store(self):
        with self.assertRaisesRegex(ValueError, "Kies deze winkel"):
            record_store_result(self.conn, "first", provider="ah", result="failed")

    def test_corrupt_state_never_silently_cleared(self):
        self.conn.settings[("first", "first_store_onboarding_v1")] = (
            '{"selected":["ah"],"results":{"jumbo":"success"}}'
        )
        with self.assertRaisesRegex(RuntimeError, "geen automatische reset"):
            read_store_onboarding(self.conn, "first")


if __name__ == "__main__":
    unittest.main()
