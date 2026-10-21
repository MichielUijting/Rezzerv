"""TD-08: isolated PostgreSQL service/ASGI regression, no operational data."""
import asyncio
import importlib.util
import os
from pathlib import Path
from threading import Event
from uuid import uuid4
import unittest
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.app.services.maintenance_runtime import start_worker, transition, state
from backend.app.services.maintenance_asgi import MaintenanceAdmissionMiddleware
from backend.app.services.maintenance_state_contract import MaintenanceTransitionError

ROOT = Path(__file__).resolve().parents[2]


class MaintenanceRuntimeIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.getenv('INHUIS_MAINTENANCE_TEST_DATABASE_URL', '')
        if not url:
            raise unittest.SkipTest('Explicit isolated maintenance test database required')
        parsed = make_url(url)
        if parsed.get_backend_name() != 'postgresql' or not (parsed.database or '').endswith('_maintenance_test'):
            raise RuntimeError('Refusing non-maintenance-test database')
        cls.base_engine = create_engine(url)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'base_engine'):
            cls.base_engine.dispose()

    def setUp(self):
        self.availability_patch = patch('backend.app.services.maintenance_runtime.read_agent_availability', return_value={'kind':'availability'})
        self.availability_patch.start(); self.addCleanup(self.availability_patch.stop)
        self.host_patch = patch('backend.app.services.maintenance_runtime.read_host_proof', return_value={'host_id':'test-host','windows_boot':'boot-test','volume_identity':'volume-test','cluster_identity':'cluster-test','domain_fingerprint':'test-fingerprint','issued_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()})
        self.host_patch.start(); self.addCleanup(self.host_patch.stop)
        self.schema = 'maintenance_runtime_test_' + uuid4().hex
        with self.base_engine.begin() as conn:
            conn.exec_driver_sql(f'CREATE SCHEMA "{self.schema}"')
        self.engine = create_engine(self.base_engine.url, connect_args={'options': f'-csearch_path={self.schema}'})
        spec = importlib.util.spec_from_file_location('maintenance_migration', ROOT/'backend/alembic/versions/20261021_01_server_maintenance.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        with self.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE test_writes(value integer)')
            conn.exec_driver_sql('CREATE TABLE test_sequence(id bigserial PRIMARY KEY,value integer)')
            conn.exec_driver_sql('CREATE TABLE household_registry(id text primary key)')
            conn.exec_driver_sql("INSERT INTO household_registry VALUES('test-a'),('test-b'),('0')")
            # The existing notification Alembic migration, not a parallel schema.
            spec = importlib.util.spec_from_file_location('notification_migration', ROOT/'backend/alembic/versions/20260926_02_household_notifications.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()
            with Operations.context(MigrationContext.configure(conn)):
                self.migration.upgrade()

    def tearDown(self):
        self.engine.dispose()
        with self.base_engine.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{self.schema}" CASCADE')

    def action(self, action, generation, **kwargs):
        with self.engine.begin() as conn:
            return transition(conn, action=action, expected_generation=generation, actor_user_id='test-platform-user', **kwargs)

    def test_announcement_and_stale_retry_are_atomic(self):
        self.action('announce', 0, announcement='Onderhoud morgen 10:00 Europe/Amsterdam, 15 minuten')
        with self.assertRaises(MaintenanceTransitionError):
            self.action('announce', 0, announcement='duplicate')
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT count(*) FROM household_notifications')).scalar_one(), 3)
            self.assertEqual(conn.execute(text('SELECT count(*) FROM maintenance_audit')).scalar_one(), 1)
        self.action('cancel', 1)
        with self.engine.connect() as conn:
            self.assertEqual(state(conn)['state'], 'normal')

    def test_worker_reservation_survives_http_handoff_and_drain(self):
        started, release = Event(), Event()
        def target():
            started.set()
            if not release.wait(10):
                raise RuntimeError('Test failed to release worker')
            from backend.app.services.maintenance_runtime import _operation
            with self.engine.begin() as conn:
                conn.execute(text("SELECT set_config('inhuis.maintenance_operation',:op,true)"), {'op':_operation.get()})
                conn.exec_driver_sql('INSERT INTO test_writes VALUES(1)')
        worker = start_worker(target=target, engine=self.engine)
        try:
            self.assertTrue(started.wait(5))
            self.action('announce', 0, announcement='Test maintenance')
            self.action('drain', 1)
            with self.assertRaises(MaintenanceTransitionError):
                self.action('prepare', 2)
            with self.assertRaises(MaintenanceTransitionError):
                start_worker(target=lambda: None, engine=self.engine)
        finally:
            release.set()
            worker.join(10)
        self.assertFalse(worker.is_alive())
        with self.engine.connect() as conn:
            self.assertEqual(state(conn)['active_operations'], 0)
            self.assertEqual(conn.execute(text('SELECT count(*) FROM test_writes')).scalar_one(), 1)

    def test_unknown_get_and_post_are_both_blocked_before_handler(self):
        self.action('announce', 0, announcement='Test maintenance')
        self.action('drain', 1)
        calls = []
        async def target(scope, receive, send):
            calls.append(scope['path'])
        app = MaintenanceAdmissionMiddleware(target, self.engine)
        async def run(method):
            messages = []
            async def send(message): messages.append(message)
            async def receive(): return {'type':'http.request','body':b''}
            await app({'type':'http','method':method,'path':'/api/unknown-future-route'}, receive, send)
            return messages
        for method in ('GET','POST','PUT','PATCH','DELETE'):
            messages = asyncio.run(run(method))
            self.assertEqual(messages[0]['status'],503)
        self.assertEqual(calls, [])

    def test_background_response_is_tracked_until_it_finishes(self):
        async def target(scope, receive, send):
            with self.engine.connect() as conn:
                self.assertEqual(state(conn)['active_operations'], 1)
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
            # Code after response includes Starlette BackgroundTasks.
            with self.engine.connect() as conn:
                self.assertEqual(state(conn)['active_operations'], 1)
        async def run():
            async def send(message): pass
            async def receive(): return {'type':'http.request','body':b''}
            await MaintenanceAdmissionMiddleware(target,self.engine)({'type':'http','method':'POST','path':'/api/test'},receive,send)
        asyncio.run(run())
        with self.engine.connect() as conn:
            self.assertEqual(state(conn)['active_operations'],0)

    def test_failed_request_leaves_unresolved_operation(self):
        async def target(scope, receive, send): raise RuntimeError('simulated crash')
        async def run():
            async def send(message): pass
            async def receive(): return {'type':'http.request','body':b''}
            await MaintenanceAdmissionMiddleware(target,self.engine)({'type':'http','method':'POST','path':'/api/test'},receive,send)
        with self.assertRaises(RuntimeError): asyncio.run(run())
        with self.engine.connect() as conn:
            self.assertEqual(state(conn)['active_operations'],1)

    def test_recovery_requires_restart_and_unchanged_database(self):
        evidence = {"database":"test", "schema_name":self.schema, "server_address":"127.0.0.1", "database_oid":"123", "alembic_heads":["test-head"], "backend_instance":"before"}
        self.action('announce',0,announcement='Test maintenance')
        self.action('drain',1)
        with patch('backend.app.services.maintenance_runtime._evidence', return_value=evidence):
            with patch('backend.app.services.maintenance_runtime._BOOT_ID', 'before'):
                self.action('prepare',2)
                with self.assertRaises(MaintenanceTransitionError): self.action('verify',3)
            with patch('backend.app.services.maintenance_runtime._BOOT_ID', 'after'):
                self.action('verify',3)
                self.action('release',4)
        with self.engine.connect() as conn:
            self.assertEqual(state(conn)['state'], 'normal')

    def test_changed_database_is_never_released(self):
        evidence = {"database":"test", "schema_name":self.schema, "server_address":"127.0.0.1", "database_oid":"123", "alembic_heads":["test-head"], "backend_instance":"before"}
        self.action('announce',0,announcement='Test maintenance')
        self.action('drain',1)
        with patch('backend.app.services.maintenance_runtime._evidence', return_value=evidence):
            self.action('prepare',2)
        with patch('backend.app.services.maintenance_runtime._evidence', return_value={**evidence,"database_oid":"wrong"}):
            with self.assertRaises(MaintenanceTransitionError): self.action('verify',3)
        with self.engine.connect() as conn:
            self.assertEqual(state(conn)['state'], 'locked')

    def test_host_archive_restores_domain_and_owned_sequences_exactly(self):
        import subprocess
        from backend.app.maintenance.server_maintenance_host_probe import collect
        from backend.app.alembic_head_authority import repository_head_revision
        container = os.getenv('INHUIS_MAINTENANCE_TEST_POSTGRES_CONTAINER','')
        if not container:
            self.skipTest('Dedicated isolated Docker service required for real pg_dump/restore')
        with self.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE alembic_version(version_num varchar(32) NOT NULL)')
            conn.execute(text('INSERT INTO alembic_version VALUES(:revision)'),{'revision':repository_head_revision()})
            conn.exec_driver_sql('INSERT INTO test_sequence(value) VALUES(9)')
        self.action('announce',0,announcement='Test maintenance')
        self.action('drain',1)
        with self.engine.begin() as conn:
            before=collect(conn)
        url=self.base_engine.url
        user=url.username
        dump=subprocess.run(['docker','exec',container,'pg_dump','-U',user,'-d',url.database,'--format=custom','--no-owner','--no-privileges'],capture_output=True,check=True,timeout=120).stdout
        self.assertTrue(dump.startswith(b'PGDMP'))
        target_name='restore_'+uuid4().hex+'_maintenance_restore_test'
        admin=create_engine(url,isolation_level='AUTOCOMMIT')
        restored_engine=None
        created=False
        try:
            with admin.connect() as conn:
                conn.exec_driver_sql('CREATE DATABASE "'+target_name+'"')
                created=True
            subprocess.run(['docker','exec','-i',container,'pg_restore','--exit-on-error','--clean','--if-exists','--no-owner','--no-privileges','-U',user,'-d',target_name],input=dump,capture_output=True,check=True,timeout=120)
            restored_engine=create_engine(url.set(database=target_name),connect_args={'options':f'-csearch_path={self.schema}'})
            with restored_engine.begin() as conn:
                after=collect(conn)
            self.assertEqual(before['domain_fingerprint'],after['domain_fingerprint'])
            self.assertTrue(any(row['table'].startswith('sequence:') for row in before['fingerprints']))
            with self.engine.begin() as conn:
                self.assertEqual(before['domain_fingerprint'],collect(conn)['domain_fingerprint'])
        finally:
            if restored_engine is not None: restored_engine.dispose()
            if created:
                with admin.connect() as conn:
                    conn.exec_driver_sql('DROP DATABASE "'+target_name+'" WITH (FORCE)')
            admin.dispose()

    def test_startup_is_durable_and_post_startup_external_writes_remain_closed(self):
        from backend.app.services.maintenance_startup import begin_startup, finish_startup, install_runtime_operation_context
        from sqlalchemy.exc import DBAPIError
        self.action('announce',0,announcement='Test maintenance')
        self.action('drain',1)
        install_runtime_operation_context(self.engine)
        begin_startup(self.engine)
        try:
            with self.engine.begin() as conn:
                self.assertEqual(state(conn)['active_operations'],1)
                conn.exec_driver_sql('INSERT INTO test_writes VALUES(7)')
        finally:
            finish_startup(self.engine)
        with self.assertRaises(DBAPIError):
            with self.engine.begin() as conn:
                conn.exec_driver_sql('INSERT INTO test_writes VALUES(8)')

    def test_missing_live_agent_never_enters_draining(self):
        from backend.app.services.maintenance_runtime_preflight import MaintenancePreflightError
        self.action('announce',0,announcement='Test maintenance')
        with patch('backend.app.services.maintenance_runtime.read_agent_availability',side_effect=MaintenancePreflightError('offline')):
            with self.assertRaises(MaintenancePreflightError): self.action('drain',1)
        with self.engine.connect() as conn:
            self.assertEqual(state(conn)['state'],'announced')

    def test_unregistered_process_write_is_rejected_by_database(self):
        from sqlalchemy.exc import DBAPIError
        self.action('announce',0,announcement='Test maintenance')
        self.action('drain',1)
        with self.assertRaises(DBAPIError):
            with self.engine.begin() as conn:
                conn.exec_driver_sql('INSERT INTO test_writes VALUES(42)')
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT count(*) FROM test_writes')).scalar_one(),0)

    def test_active_downgrade_is_refused_without_data_loss(self):
        self.action('announce',0,announcement='Test maintenance')
        with self.assertRaises(RuntimeError):
            with self.engine.begin() as conn:
                with Operations.context(MigrationContext.configure(conn)):
                    self.migration.downgrade()
        with self.engine.connect() as conn:
            self.assertEqual(state(conn)['state'],'announced')
