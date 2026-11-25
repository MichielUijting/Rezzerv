"""Household-scoped store choice, proof, and recovery service contract.

These SQLite tests exercise the portable DML-only state operations. Production
PostgreSQL and end-to-end authorization are covered by the normal PR gates.
No real user data, retailer accounts, or receipt payloads are involved.
"""
from __future__ import annotations

import unittest

from sqlalchemy import create_engine, text

from app.services.store_onboarding_progress_service import (
    read_store_onboarding,
    record_store_result,
    seed_store_onboarding,
    update_store_selection,
)


class StoreOnboardingProgressTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE household_settings (
                    id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL,
                    setting_key TEXT NOT NULL,
                    setting_value TEXT NOT NULL,
                    updated_at TEXT,
                    UNIQUE (household_id, setting_key)
                )
            """))
            conn.execute(text("""
                CREATE TABLE retailer_account_credentials (
                    household_id TEXT NOT NULL, provider TEXT NOT NULL,
                    UNIQUE (household_id, provider)
                )
            """))
            conn.execute(text("""
                CREATE TABLE retailer_import_queue (
                    id TEXT PRIMARY KEY, household_id TEXT NOT NULL,
                    provider TEXT NOT NULL
                )
            """))
            seed_store_onboarding(conn, "first")
            seed_store_onboarding(conn, "second")
        self.addCleanup(self.engine.dispose)

    def test_only_explicitly_seeded_households_are_available(self):
        with self.engine.connect() as conn:
            self.assertEqual(read_store_onboarding(conn, "legacy"), {
                "available": False, "selected": [], "results": {},
            })
            self.assertEqual(read_store_onboarding(conn, "first"), {
                "available": True, "selected": [], "results": {},
            })
            self.assertEqual(read_store_onboarding(conn, "second")["selected"], [])

    def test_seed_is_idempotent_and_never_resets_progress(self):
        with self.engine.begin() as conn:
            update_store_selection(conn, "first", ["ah", "jumbo"])
            seed_store_onboarding(conn, "first")
            self.assertEqual(read_store_onboarding(conn, "first")["selected"], ["ah", "jumbo"])

    def test_selection_can_be_multiple_and_survives_new_transaction(self):
        with self.engine.begin() as conn:
            update_store_selection(conn, "first", ["lidl", "ah"])
        with self.engine.connect() as conn:
            self.assertEqual(read_store_onboarding(conn, "first")["selected"], ["ah", "lidl"])
            self.assertEqual(read_store_onboarding(conn, "second")["selected"], [])

    def test_unseeded_household_cannot_opt_in_by_write(self):
        with self.engine.begin() as conn, self.assertRaisesRegex(ValueError, "niet actief"):
            update_store_selection(conn, "legacy", ["ah"])

    def test_invalid_or_duplicate_selection_fails_closed(self):
        with self.engine.begin() as conn:
            for invalid in (["ah", "ah"], ["plus"], ["lidl", "aldi"]):
                with self.assertRaises(ValueError):
                    update_store_selection(conn, "first", invalid)

    def test_failed_result_is_resumable_with_no_false_success(self):
        with self.engine.begin() as conn:
            update_store_selection(conn, "first", ["lidl"])
            result = record_store_result(conn, "first", provider="lidl", result="failed")
            self.assertEqual(result["results"], {"lidl": "failed"})
        with self.engine.connect() as conn:
            self.assertEqual(read_store_onboarding(conn, "first")["results"]["lidl"], "failed")

    def test_ah_success_requires_own_household_credential(self):
        with self.engine.begin() as conn:
            update_store_selection(conn, "first", ["ah"])
            conn.execute(text("""
                INSERT INTO retailer_account_credentials (household_id, provider)
                VALUES ('second', 'ah')
            """))
            with self.assertRaisesRegex(ValueError, "niet door Inhuis bevestigd"):
                record_store_result(conn, "first", provider="ah", result="success")
            conn.execute(text("""
                INSERT INTO retailer_account_credentials (household_id, provider)
                VALUES ('first', 'ah')
            """))
            result = record_store_result(conn, "first", provider="ah", result="success")
            self.assertEqual(result["results"]["ah"], "success")
            with self.assertRaises(ValueError):
                update_store_selection(conn, "first", [])
            # Repeated proof is idempotent and success cannot be demoted.
            self.assertEqual(record_store_result(conn, "first", provider="ah", result="failed")["results"]["ah"], "success")

    def test_jumbo_lidl_success_requires_matching_queue_and_household(self):
        with self.engine.begin() as conn:
            update_store_selection(conn, "first", ["jumbo", "lidl"])
            conn.execute(text("""
                INSERT INTO retailer_import_queue (id, household_id, provider)
                VALUES ('other-house', 'second', 'jumbo'),
                       ('wrong-provider', 'first', 'lidl'),
                       ('valid-jumbo', 'first', 'jumbo')
            """))
            for receipt_id in (None, "other-house", "wrong-provider"):
                with self.assertRaises(ValueError):
                    record_store_result(conn, "first", provider="jumbo", result="success", queue_id=receipt_id)
            result = record_store_result(
                conn, "first", provider="jumbo", result="success", queue_id="valid-jumbo",
            )
            self.assertEqual(result["results"], {"jumbo": "success"})
            self.assertEqual(result["selected"], ["jumbo", "lidl"])
            self.assertEqual(read_store_onboarding(conn, "second")["results"], {})

    def test_unselected_result_cannot_be_recorded(self):
        with self.engine.begin() as conn, self.assertRaisesRegex(ValueError, "Kies deze winkel"):
            record_store_result(conn, "first", provider="ah", result="failed")

    def test_corrupted_data_is_not_silently_reset(self):
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE household_settings
                SET setting_value = '{"selected":["ah"],"results":{"jumbo":"success"}}'
                WHERE household_id = 'first'
            """))
            with self.assertRaisesRegex(RuntimeError, "geen automatische reset"):
                read_store_onboarding(conn, "first")


if __name__ == "__main__":
    unittest.main()
