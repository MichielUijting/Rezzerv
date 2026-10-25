"""Schema shape checks without touching an application database."""
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch
from backend.app.services.maintenance_schema_contract import maintenance_metadata


class MaintenanceSchemaContractTest(unittest.TestCase):
    def profile_barrier_migration(self):
        path = Path(__file__).resolve().parents[1]/'alembic/versions/20261023_02_consumption_profile_write_barrier.py'
        spec = importlib.util.spec_from_file_location('profile_barrier_migration', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_profile_barrier_is_migration_owned_schema_qualified_and_symmetric(self):
        from sqlalchemy.dialects.postgresql import dialect
        module = self.profile_barrier_migration()
        conn = Mock()
        conn.dialect = dialect()
        conn.execute.return_value.scalar_one.return_value = 'isolated"schema'
        with patch.object(module.op, 'get_bind', return_value=conn):
            module.upgrade()
            module.downgrade()
        create, drop = [call.args[0] for call in conn.exec_driver_sql.call_args_list]
        self.assertIn('BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE', create)
        self.assertIn('ON "isolated""schema".global_product_consumption_profiles', create)
        self.assertIn('EXECUTE FUNCTION "isolated""schema".inhuis_maintenance_write_barrier()', create)
        self.assertEqual(drop, 'DROP TRIGGER inhuis_maintenance_write_gate ON "isolated""schema".global_product_consumption_profiles')
        self.assertEqual(module.down_revision, '20261023_01')

    def test_profile_barrier_does_not_emit_postgresql_ddl_for_legacy_sqlite(self):
        module = self.profile_barrier_migration()
        conn = Mock()
        conn.dialect.name = 'sqlite'
        with patch.object(module.op, 'get_bind', return_value=conn):
            module.upgrade()
            module.downgrade()
        conn.execute.assert_not_called()
        conn.exec_driver_sql.assert_not_called()

    def test_control_and_operation_columns(self):
        tables = maintenance_metadata.tables
        self.assertEqual(set(tables), {"maintenance_control", "maintenance_operations", "maintenance_audit"})
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
