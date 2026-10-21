"""Unit-level contract tests; PostgreSQL concurrency integration still required."""
import unittest
from unittest.mock import Mock
from backend.app.services.maintenance_postgres_admission import (
    admit_operation, begin_draining, outstanding_operations,
)
from backend.app.services.maintenance_state_contract import MaintenanceTransitionError


class AdmissionTests(unittest.TestCase):
    def test_reject_when_draining(self):
        conn = Mock()
        conn.execute.return_value.mappings.return_value.one_or_none.return_value = {
            "state": "draining", "generation": 4
        }
        with self.assertRaises(MaintenanceTransitionError):
            admit_operation(conn, kind="receipt_import")
        self.assertEqual(conn.execute.call_count, 1)

    def test_missing_control_row_fails_closed(self):
        conn = Mock()
        conn.execute.return_value.mappings.return_value.one_or_none.return_value = None
        with self.assertRaises(MaintenanceTransitionError):
            admit_operation(conn, kind="inventory")

    def test_generation_compare_and_swap(self):
        conn = Mock()
        conn.execute.return_value.mappings.return_value.one_or_none.return_value = {
            "state": "announced", "generation": 7
        }
        with self.assertRaises(MaintenanceTransitionError):
            begin_draining(conn, expected_generation=6)
        self.assertEqual(conn.execute.call_count, 1)

    def test_draining_transition(self):
        conn = Mock()
        conn.execute.return_value.mappings.return_value.one_or_none.return_value = {
            "state": "announced", "generation": 7
        }
        self.assertEqual(begin_draining(conn, expected_generation=7), 8)
        self.assertEqual(conn.execute.call_count, 2)

    def test_stale_operations_block(self):
        conn = Mock()
        conn.execute.return_value.scalar_one.return_value = 2
        self.assertEqual(outstanding_operations(conn), 2)


if __name__ == "__main__":
    unittest.main()
