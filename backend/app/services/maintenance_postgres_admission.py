"""PostgreSQL maintenance admission primitive (not yet mounted in Inhuis).

Requires Alembic-owned tables maintenance_control (singleton id=1, state, generation)
and maintenance_operations (operation_id, generation, kind, started_at,
finished_at). No runtime schema creation; no polling of process-local counters.
Do not use until schema, worker coverage and isolation tests are complete.
"""
from __future__ import annotations

from uuid import uuid4
from sqlalchemy import text
from .maintenance_state_contract import MaintenanceState, MaintenanceTransitionError

_CONTROL = "SELECT state, generation FROM maintenance_control WHERE id=1 FOR UPDATE"


def admit_operation(conn, *, kind: str) -> str:
    """Atomically register a writer within caller's transaction.

    IMPORTANT: registration must commit *before* the work starts; the caller
    must retain a durable operation until all work and side effects finish.
    """
    # Reject an already closed gate without waiting behind a prepare lock.
    # The locked recheck below remains the admission authority in every race.
    visible = conn.execute(text('SELECT state FROM maintenance_control WHERE id=1')).mappings().one_or_none()
    if visible is None:
        raise MaintenanceTransitionError('Onderhoudsstatus ontbreekt')
    if MaintenanceState(visible['state']) not in (MaintenanceState.NORMAL, MaintenanceState.ANNOUNCED):
        raise MaintenanceTransitionError('Nieuwe verwerking geblokkeerd wegens onderhoud')
    row = conn.execute(text(_CONTROL)).mappings().one_or_none()
    if row is None:
        raise MaintenanceTransitionError("Onderhoudsstatus ontbreekt")
    if MaintenanceState(row["state"]) not in (MaintenanceState.NORMAL, MaintenanceState.ANNOUNCED):
        raise MaintenanceTransitionError("Nieuwe verwerking geblokkeerd wegens onderhoud")
    operation_id = str(uuid4())
    conn.execute(text("""
        INSERT INTO maintenance_operations
          (operation_id, generation, kind, started_at, finished_at)
        VALUES (:operation_id, :generation, :kind, CURRENT_TIMESTAMP, NULL)
    """), {"operation_id": operation_id, "generation": row["generation"], "kind": kind})
    return operation_id


def begin_draining(conn, *, expected_generation: int) -> int:
    """CAS on locked control row. Commit before advertising draining.

    Concurrent admissions serialize on the same row; admitted operations must
    finish separately before maintenance can be locked.
    """
    row = conn.execute(text(_CONTROL)).mappings().one_or_none()
    if row is None or row["generation"] != expected_generation:
        raise MaintenanceTransitionError("Onderhoudsgeneratie gewijzigd")
    if MaintenanceState(row["state"]) != MaintenanceState.ANNOUNCED:
        raise MaintenanceTransitionError("Onderhoud niet aangekondigd")
    next_generation = expected_generation + 1
    conn.execute(text("""
        UPDATE maintenance_control SET state='draining', generation=:generation
        WHERE id=1
    """), {"generation": next_generation})
    return next_generation


def complete_operation(conn, *, operation_id: str) -> None:
    """End a known operation; crash recovery requires separate reconciliation."""
    result = conn.execute(text("""
        UPDATE maintenance_operations SET finished_at=CURRENT_TIMESTAMP
        WHERE operation_id=:operation_id AND finished_at IS NULL
    """), {"operation_id": operation_id})
    if result.rowcount != 1:
        raise MaintenanceTransitionError("Verwerking niet gevonden of al afgesloten")


def outstanding_operations(conn) -> int:
    """All generations are considered: stale entries must block reboot."""
    return int(conn.execute(text("""
        SELECT COUNT(*) FROM maintenance_operations WHERE finished_at IS NULL
    """)).scalar_one())
