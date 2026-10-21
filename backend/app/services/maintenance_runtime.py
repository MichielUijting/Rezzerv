"""TD-05: durable request/job admission and maintenance transitions.

Every admitted operation remains durable until its entire ASGI call or worker
returns. A crash leaves an unfinished operation; expiry never proves success.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from threading import Thread
from uuid import uuid4

from sqlalchemy import text

from .maintenance_postgres_admission import admit_operation, complete_operation, outstanding_operations
from .maintenance_runtime_preflight import read_runtime_schema_evidence, MaintenancePreflightError
from .maintenance_state_contract import MaintenanceTransitionError
from .maintenance_host_proof import read_host_proof, read_agent_availability

_operation = ContextVar("inhuis_maintenance_operation", default=None)
_BOOT_ID = str(uuid4())  # Backend instance identity, explicitly NOT a Windows boot proof.


def _engine():
    from app.db import engine
    return engine



def writer_operation(function):
    """Protect direct CLI/import callers before file/network/domain side effects."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        engine = _engine()
        if engine.dialect.name != 'postgresql' or _operation.get():
            return function(*args, **kwargs)
        with engine.begin() as conn:
            op = admit_operation(conn,kind=('call:'+function.__name__)[:100])
        token = _operation.set(op)
        try:
            result = function(*args, **kwargs)
        except BaseException:
            raise  # unresolved, never a successful/expired lease
        else:
            with engine.begin() as conn:
                complete_operation(conn,operation_id=op)
            return result
        finally:
            _operation.reset(token)
    return wrapped


def start_worker(*, target, args=(), name=None, daemon=True, engine=None):
    """Reserve BEFORE thread start; release only after target and all its writes.

    A child of an admitted request may be handed off during draining. The parent
    cannot finish before this reservation commits, closing the HTTP/thread gap.
    """
    engine = engine or _engine()
    if engine.dialect.name != "postgresql":
        worker = Thread(target=target, args=args, name=name, daemon=daemon)
        worker.start()
        return worker
    with engine.begin() as conn:
        row = conn.execute(text("SELECT state,generation FROM maintenance_control WHERE id=1 FOR UPDATE")).mappings().one()
        parent = _operation.get()
        inherited = parent and conn.execute(text("SELECT 1 FROM maintenance_operations WHERE operation_id=:id AND finished_at IS NULL"), {"id": parent}).scalar()
        if not inherited and row["state"] not in {"normal", "announced"}:
            raise MaintenanceTransitionError("Nieuwe achtergrondtaak geblokkeerd wegens onderhoud")
        if row["state"] not in {"normal", "announced", "draining"}:
            raise MaintenanceTransitionError("Onderhoud is vergrendeld")
        op = str(uuid4())
        conn.execute(text("INSERT INTO maintenance_operations(operation_id,generation,kind,started_at) VALUES(:id,:generation,:kind,CURRENT_TIMESTAMP)"), {"id":op,"generation":row["generation"],"kind":("worker:"+(name or target.__name__))[:100]})
    def run():
        token = _operation.set(op)
        try:
            target(*args)
        except BaseException:
            # Uncaught worker failure is unresolved, never a successful drain.
            raise
        else:
            with engine.begin() as conn:
                complete_operation(conn, operation_id=op)
        finally:
            _operation.reset(token)
    worker = Thread(target=run, name=name, daemon=daemon)
    try:
        worker.start()
    except BaseException:
        with engine.begin() as conn:
            complete_operation(conn, operation_id=op)
        raise
    return worker


def state(conn):
    row = conn.execute(text("SELECT state,generation,cycle_id,announcement,evidence_json,locked_boot_id,updated_at FROM maintenance_control WHERE id=1")).mappings().one()
    result = {key:value for key,value in dict(row).items() if key not in {'evidence_json','locked_boot_id'}}
    try:
        read_agent_availability()
        result['host_agent_ready'] = True
    except MaintenancePreflightError:
        result['host_agent_ready'] = False
    result['restart_detected'] = bool(row['locked_boot_id'] and row['locked_boot_id'] != _BOOT_ID)
    result.update(active_operations=outstanding_operations(conn), restart_allowed=False)
    if row['state'] == 'locked' and not result['active_operations']:
        try:
            evidence = json.loads(row['evidence_json'] or '{}')
            live = _evidence(conn)
            proof = read_host_proof(cycle_id=row['cycle_id'], runtime=live)
            issued = datetime.fromisoformat(proof['issued_at'].replace('Z','+00:00'))
            result['restart_valid_for_seconds'] = max(0, 90-(datetime.now(timezone.utc)-issued).total_seconds())
            result['restart_allowed'] = all(proof[key] == evidence['host'][key] for key in ('host_id','windows_boot','volume_identity','cluster_identity','domain_fingerprint'))
        except Exception:
            pass
    return result


def _broadcast(conn, message, generation):
    from .household_notification_service import publish_household_notification
    # Existing notification inbox projects a household broadcast to EVERY member,
    # including users joining after announcement. No new communication system.
    households = conn.execute(text("SELECT id FROM household_registry")).scalars().all()
    for household in households:
        publish_household_notification(conn, household_id=household, category="serveronderhoud", title="Serveronderhoud Inhuis", message=message, source_type="server_maintenance", source_key=str(generation))


def _evidence(conn):
    from .maintenance_startup import assert_write_barrier
    assert_write_barrier(conn)
    evidence = read_runtime_schema_evidence(conn, alembic_ini=Path(__file__).resolve().parents[2]/"alembic.ini")
    evidence["release_version"] = (Path(__file__).resolve().parents[2]/"VERSION.txt").read_text().strip()
    # The signed host evidence independently binds this connection to storage.
    evidence["database_oid"] = str(conn.execute(text("SELECT oid FROM pg_database WHERE datname=current_database()" )).scalar_one())
    active = conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND (state IS DISTINCT FROM 'idle' OR xact_start IS NOT NULL)" )).scalar_one()
    if active:
        raise MaintenancePreflightError("Andere databasesessies zijn nog actief; wacht en controleer opnieuw")
    if conn.execute(text("SELECT count(*) FROM pg_prepared_xacts WHERE database=current_database()" )).scalar_one():
        raise MaintenancePreflightError("Voorbereide databasetransacties blokkeren onderhoud")
    evidence["backend_instance"] = _BOOT_ID
    return evidence


def transition(conn, *, action, expected_generation, actor_user_id, announcement=""):
    conn.execute(text("SET LOCAL lock_timeout='3s'"))
    conn.execute(text("SELECT set_config('inhuis.maintenance_admin', '1', true)"))
    row = conn.execute(text("SELECT * FROM maintenance_control WHERE id=1 FOR UPDATE")).mappings().one()
    if row["generation"] != expected_generation:
        raise MaintenanceTransitionError("Status is gewijzigd. Vernieuw het scherm.")
    current = row["state"]
    target = None
    evidence = None
    cycle_id = row["cycle_id"]
    if action == "announce" and current == "normal":
        if not announcement.strip():
            raise MaintenanceTransitionError("Vul het onderhoudsvenster en de verwachte duur in")
        target = "announced"
        cycle_id = str(uuid4())
    elif action == "cancel" and current == "announced":
        target = "normal"
    elif action == "drain" and current == "announced":
        read_agent_availability()
        target = "draining"
    elif action == "prepare" and current in {"draining", "locked"}:
        if outstanding_operations(conn):
            raise MaintenanceTransitionError("Lopende verwerkingen zijn nog niet afgerond")
        evidence = _evidence(conn)
        evidence["host"] = read_host_proof(cycle_id=cycle_id, runtime=evidence)
        target = "locked"
    elif action == "verify" and current in {"locked", "verifying", "blocked"}:
        if outstanding_operations(conn):
            raise MaintenanceTransitionError("Onvoltooide verwerkingen vereisen onderzoek; geen automatische vrijgave")
        previous = json.loads(row["evidence_json"] or "{}")
        evidence = _evidence(conn)
        if not previous or previous.get("backend_instance") == _BOOT_ID:
            raise MaintenanceTransitionError("De backend is nog niet herstart")
        for key in ("database", "schema_name", "database_oid", "alembic_heads", "release_version"):
            if evidence.get(key) != previous.get(key):
                raise MaintenanceTransitionError("De actieve database of software wijkt af van het onderhoudsbewijs")
        read_host_proof(cycle_id=cycle_id, runtime=evidence, previous=previous["host"])
        target = "verifying"
        # Retain original pre-restart evidence until release, for repeatable checks.
        evidence = previous
    elif action == "release" and current == "verifying":
        if outstanding_operations(conn):
            raise MaintenanceTransitionError("Er zijn nog onvoltooide verwerkingen")
        previous = json.loads(row["evidence_json"] or "{}")
        live = _evidence(conn)
        if previous.get("backend_instance") == _BOOT_ID:
            raise MaintenanceTransitionError("Herstartbewijs ontbreekt")
        for key in ("database", "schema_name", "database_oid", "alembic_heads", "release_version"):
            if previous.get(key) != live.get(key):
                raise MaintenanceTransitionError("Herstelcontrole is niet meer geldig")
        read_host_proof(cycle_id=cycle_id, runtime=live, previous=previous["host"])
        target = "normal"
    if target is None:
        raise MaintenanceTransitionError("Deze onderhoudsactie is nu niet toegestaan")
    generation = expected_generation + 1
    messages = {"announce": announcement.strip(), "cancel": "Het aangekondigde serveronderhoud is geannuleerd.", "drain": "Serveronderhoud is begonnen. Nieuwe verwerkingen zijn tijdelijk geblokkeerd. Lopend werk wordt afgerond.", "release": "Het onderhoud aan Inhuis is afgerond. De applicatie is weer beschikbaar."}
    if action in messages:
        _broadcast(conn, messages[action], generation)
    conn.execute(text("UPDATE maintenance_control SET state=:state,generation=:generation,cycle_id=:cycle_id,announcement=:announcement,evidence_json=:evidence,locked_boot_id=:boot,updated_at=CURRENT_TIMESTAMP WHERE id=1"), {"state":target,"generation":generation,"cycle_id":cycle_id,"announcement":announcement.strip() if action=="announce" else row["announcement"],"evidence":json.dumps(evidence) if evidence else row["evidence_json"],"boot":_BOOT_ID if action=="prepare" else row["locked_boot_id"]})
    conn.execute(text("INSERT INTO maintenance_audit(id,generation,actor_user_id,action) VALUES(:id,:generation,:actor,:action)"), {"id":str(uuid4()),"generation":generation,"actor":actor_user_id,"action":action})
    result = state(conn)
    result["runtime_checks_passed"] = action == "prepare"
    return result
