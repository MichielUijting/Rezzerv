"""Regression: unchanged authorization grants must retain their original created_at."""
import unittest

from sqlalchemy import create_engine, text
from backend.app.services.authorization_foundation_service import _seed_registry, ROLE_PERMISSIONS


class AuthorizationBootstrapIdempotenceTest(unittest.TestCase):
    def test_seed_does_not_recreate_unchanged_permissions(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.begin() as conn:
            conn.exec_driver_sql("""CREATE TABLE auth_roles (
                role_key TEXT PRIMARY KEY, scope TEXT, name TEXT, active BOOLEAN DEFAULT 1)""")
            conn.exec_driver_sql("""CREATE TABLE auth_permissions (
                permission_key TEXT PRIMARY KEY, scope TEXT, description TEXT,
                active BOOLEAN DEFAULT 1)""")
            conn.exec_driver_sql("""CREATE TABLE auth_role_permissions (
                role_key TEXT NOT NULL, permission_key TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (role_key, permission_key))""")
            _seed_registry(conn)
            expected_count = sum(len(permissions) for permissions in ROLE_PERMISSIONS.values())
            self.assertEqual(conn.scalar(text("SELECT COUNT(*) FROM auth_role_permissions")), expected_count)
            conn.execute(text("UPDATE auth_role_permissions SET created_at = '2001-01-01 00:00:00'"))
            _seed_registry(conn)
            self.assertEqual(conn.scalar(text("SELECT COUNT(*) FROM auth_role_permissions")), expected_count)
            self.assertEqual(conn.scalar(text("""
                SELECT COUNT(*) FROM auth_role_permissions
                WHERE created_at <> '2001-01-01 00:00:00'
            """)), 0)


if __name__ == "__main__":
    unittest.main()
