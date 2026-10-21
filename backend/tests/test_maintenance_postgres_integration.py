"""Integration tests of maintenance admission against an expendable PostgreSQL DB.

Explicit opt-in only:
  INHUIS_MAINTENANCE_TEST_DATABASE_URL=postgresql+psycopg://.../some_maintenance_test
  python -m unittest backend.tests.test_maintenance_postgres_integration

Each test creates and removes ONLY its own randomly named schema inside that
test database. Never point this to an Inhuis operational database.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.app.services.maintenance_postgres_admission import (
    admit_operation, begin_draining, complete_operation, outstanding_operations,
)
from backend.app.services.maintenance_state_contract import MaintenanceTransitionError


class AdmissionPostgresIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.getenv("INHUIS_MAINTENANCE_TEST_DATABASE_URL", "").strip()
        if not url:
            raise unittest.SkipTest("Geen geisoleerde PostgreSQL testdatabase opgegeven")
        parsed = make_url(url)
        if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith("_maintenance_test"):
            raise unittest.SkipTest("Alleen een expliciete PostgreSQL-database eindigend op _maintenance_test is toegestaan")
        cls.engine = create_engine(url, pool_size=3, max_overflow=0, connect_args={"connect_timeout": 5})

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "engine"):
            cls.engine.dispose()

    def setUp(self):
        self.schema = "maintenance_test_" + uuid4().hex
        with self.engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{self.schema}"')
            conn.exec_driver_sql(f"""
                CREATE TABLE "{self.schema}".maintenance_control
                (id integer PRIMARY KEY CHECK(id=1), state text NOT NULL, generation integer NOT NULL)
            """)
            conn.exec_driver_sql(f"""
                CREATE TABLE "{self.schema}".maintenance_operations
                (operation_id text PRIMARY KEY, generation integer NOT NULL,
                 kind text NOT NULL, started_at timestamptz NOT NULL,
                 finished_at timestamptz)
            """)
            conn.exec_driver_sql(f"""
                INSERT INTO "{self.schema}".maintenance_control VALUES (1, 'announced', 1)
            """)

    def tearDown(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{self.schema}" CASCADE')

    def _conn(self):
        conn = self.engine.connect()
        conn.exec_driver_sql(f'SET search_path TO "{self.schema}"')
        conn.commit()
        return conn

    def test_drain_blocks_new_writer_but_tracks_previous_writer(self):
        with self._conn() as conn:
            with conn.begin():
                operation_id = admit_operation(conn, kind="zip_receipt_import")
        with self._conn() as conn:
            with conn.begin():
                self.assertEqual(begin_draining(conn, expected_generation=1), 2)
        with self._conn() as conn:
            self.assertEqual(outstanding_operations(conn), 1)
            with self.assertRaises(MaintenanceTransitionError):
                with conn.begin():
                    admit_operation(conn, kind="inventory")
            conn.rollback()
            with conn.begin():
                complete_operation(conn, operation_id=operation_id)
            self.assertEqual(outstanding_operations(conn), 0)

    def test_drain_serializes_against_inflight_admission(self):
        admitted = Event()
        release = Event()

        def writer():
            with self._conn() as conn:
                with conn.begin():
                    op_id = admit_operation(conn, kind="receipt")
                    admitted.set()
                    if not release.wait(10):
                        raise TimeoutError("Writer was not released")
            return op_id

        def drainer():
            with self._conn() as conn:
                with conn.begin():
                    return begin_draining(conn, expected_generation=1)

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_writer = pool.submit(writer)
            self.assertTrue(admitted.wait(10))
            future_drain = pool.submit(drainer)
            release.set()
            operation_id = future_writer.result(timeout=10)
            self.assertEqual(future_drain.result(timeout=10), 2)
        with self._conn() as conn:
            self.assertEqual(outstanding_operations(conn), 1)
            with conn.begin():
                complete_operation(conn, operation_id=operation_id)


if __name__ == "__main__":
    unittest.main()
