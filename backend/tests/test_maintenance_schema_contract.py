"""Schema shape checks without touching an application database."""
import unittest
from backend.app.services.maintenance_schema_contract import maintenance_metadata


class MaintenanceSchemaContractTest(unittest.TestCase):
    def test_control_and_operation_columns(self):
        tables = maintenance_metadata.tables
        self.assertEqual(set(tables), {"maintenance_control", "maintenance_operations"})
        control = tables["maintenance_control"]
        operations = tables["maintenance_operations"]
        self.assertTrue({"id", "state", "generation", "updated_at"} <= set(control.c.keys()))
        self.assertTrue({"operation_id", "generation", "kind", "started_at", "finished_at"} <= set(operations.c.keys()))
        self.assertFalse(control.c.state.nullable)
        self.assertFalse(operations.c.kind.nullable)

    def test_prevent_unknown_state_or_negative_generation(self):
        names = {constraint.name for t in maintenance_metadata.tables.values() for constraint in t.constraints}
        self.assertIn("ck_maintenance_valid_state", names)
        self.assertIn("ck_maintenance_generation_nonnegative", names)
        self.assertIn("ck_maintenance_operation_generation", names)


if __name__ == "__main__":
    unittest.main()
