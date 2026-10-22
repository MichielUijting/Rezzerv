"""TD-05: durable startup coverage, including legacy installer threads.

Installed before importing app.main. No schema creation, migration or stale-lease
expiry. A failed startup remains unresolved and prevents maintenance approval.
"""
from __future__ import annotations

import threading
import time
from uuid import uuid4
from sqlalchemy import event, text

from .maintenance_runtime import _operation
from .maintenance_postgres_admission import complete_operation

_startup_operation = None


def install_runtime_operation_context(engine):
    if engine.dialect.name != 'postgresql':
        return
    @event.listens_for(engine, 'begin')
    def bind_operation(conn):
        op = _operation.get() or _startup_operation or ''
        conn.execute(text("SELECT set_config('inhuis.maintenance_operation', :op, true)"), {'op':op})
        conn.execute(text("SELECT set_config('inhuis.maintenance_admin', '', true)"))


def begin_startup(engine):
    global _startup_operation
    if engine.dialect.name != 'postgresql':
        return
    op = str(uuid4())
    with engine.begin() as conn:
        assert_write_barrier(conn)
        row = conn.execute(text('SELECT generation FROM maintenance_control WHERE id=1 FOR UPDATE')).mappings().one()
        conn.execute(text("INSERT INTO maintenance_operations(operation_id,generation,kind,started_at) VALUES(:op,:generation,'startup',CURRENT_TIMESTAMP)"), {'op':op,'generation':row['generation']})
    _startup_operation = op


def finish_startup(engine):
    global _startup_operation
    if engine.dialect.name != 'postgresql':
        return
    deadline = time.monotonic() + 30
    # app.__init__ only starts the inspected _install* compatibility installers.
    # Wait for their actual return, not merely for main.app to become visible.
    for thread in threading.enumerate():
        if thread is not threading.current_thread() and any(name in thread.name for name in ('(_install', '(_deduplicate_receipt_parser_diagnosis_routes_when_ready')):
            thread.join(max(0, deadline-time.monotonic()))
            if thread.is_alive():
                raise RuntimeError('Startup-installatie nog actief; onderhoud blijft geblokkeerd')
    with engine.begin() as conn:
        complete_operation(conn, operation_id=_startup_operation)
    _startup_operation = None


def assert_write_barrier(conn):
    missing = conn.execute(text("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=current_schema() AND c.relkind IN ('r','p')
        AND c.relname NOT IN ('maintenance_control','maintenance_operations','maintenance_audit','server_sessions','auth_audit_log','alembic_version')
        AND NOT EXISTS(SELECT 1 FROM pg_trigger t WHERE t.tgrelid=c.oid
          AND t.tgname='inhuis_maintenance_write_gate' AND t.tgenabled='O')
    """)).scalars().all()
    if missing:
        raise RuntimeError('Niet alle tabellen hebben de onderhoudsbarriere; startup gestopt')
