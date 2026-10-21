"""Unit tests for execution-time, read-only maintenance preflight."""
import unittest
from unittest.mock import Mock, patch

from backend.app.services.maintenance_runtime_preflight import (
    MaintenancePreflightError,
    read_runtime_schema_evidence,
)


class MaintenanceRuntimePreflightTest(unittest.TestCase):
    def setUp(self):
        self.connection = Mock()
        self.connection.dialect.name = "postgresql"
        self.connection.execute.side_effect = [
            Mock(**{"mappings.return_value.one.return_value": {
                "database": "rezzerv_test", "schema_name": "public",
                "server_address": "127.0.0.1", "server_started_at": "2026-10-21",
            }}),
            Mock(**{"scalars.return_value.all.return_value": ["rev_test"]}),
        ]

    @patch("backend.app.services.maintenance_runtime_preflight.ScriptDirectory.from_config")
    def test_actual_database_version_is_evaluated_during_call(self, directory):
        directory.return_value.get_heads.return_value = ["rev_test"]
        result = read_runtime_schema_evidence(self.connection, alembic_ini="/tmp/alembic.ini")
        self.assertTrue(result["schema_compatible"])
        self.assertEqual(result["alembic_heads"], ["rev_test"])
        self.assertEqual(self.connection.execute.call_count, 2)
        for call in self.connection.execute.call_args_list:
            sql = str(call.args[0]).lower()
            self.assertTrue(sql.strip().startswith("select"))
            self.assertNotIn("migration_database_url", sql)

    @patch("backend.app.services.maintenance_runtime_preflight.ScriptDirectory.from_config")
    def test_revision_mismatch_blocks(self, directory):
        directory.return_value.get_heads.return_value = ["new_revision"]
        with self.assertRaises(MaintenancePreflightError):
            read_runtime_schema_evidence(self.connection, alembic_ini="/tmp/alembic.ini")

    def test_non_postgresql_blocks_before_database_query(self):
        self.connection.dialect.name = "sqlite"
        with self.assertRaises(MaintenancePreflightError):
            read_runtime_schema_evidence(self.connection, alembic_ini="/tmp/alembic.ini")
        self.connection.execute.assert_not_called()

    @patch("backend.app.services.maintenance_runtime_preflight.ScriptDirectory.from_config")
    def test_unreadable_live_schema_blocks(self, directory):
        directory.return_value.get_heads.return_value = ["rev_test"]
        self.connection.execute.side_effect = RuntimeError("db offline")
        with self.assertRaises(MaintenancePreflightError):
            read_runtime_schema_evidence(self.connection, alembic_ini="/tmp/alembic.ini")


if __name__ == "__main__":
    unittest.main()
