"""Household-scoped, fail-closed Jumbo history continuation.

Queue acknowledgement is only durable staging; the browser's complete scan
and the worker's completed statuses are independent prerequisites for releasing
an earlier pending window. Never infer completeness from a MAX(receipt date).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

from app.services.retailer_receipt_import_dates import latest_retailer_import_dates

MAX_HISTORY_RECEIPTS = 2000


def _queue_completed(conn, household_id: str, queue_ids: list[str]) -> bool:
    if not queue_ids:
        return True
    result = conn.execute(
        text("""
            SELECT id,status FROM retailer_import_queue
            WHERE household_id=:household_id AND provider='jumbo'
              AND id IN :queue_ids
        """).bindparams(bindparam("queue_ids", expanding=True)),
        {"household_id": household_id, "queue_ids": queue_ids},
    ).mappings().all()
    return len(result) == len(queue_ids) and all(
        str(row["status"]) == "completed" for row in result
    )


def begin_jumbo_history(engine: Engine, household_id: str) -> dict:
    """Reserve an inclusive start; retain the oldest unfinished range."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Jumbo-historie vereist duurzame PostgreSQL-opslag")
    today = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    latest = latest_retailer_import_dates(engine, household_id=household_id)["jumbo"]
    first = date.fromisoformat(latest) if latest is not None else date(today.year - 1, 1, 1)
    if first > today:
        raise ValueError("Ongeldige Jumbo-aankoopdatum in de historie")
    run_id = str(uuid4())
    with engine.begin() as conn:
        old = conn.execute(text("""
            SELECT pending_from_date,scan_complete,queue_ids
            FROM household_jumbo_import_runs
            WHERE household_id=:household_id FOR UPDATE
        """), {"household_id": household_id}).mappings().first()
        pending = old["pending_from_date"] if old else None
        cleared = False
        if old and bool(old["scan_complete"]):
            queue_ids = old["queue_ids"]
            if not isinstance(queue_ids, list) or len(queue_ids) > MAX_HISTORY_RECEIPTS:
                raise ValueError("Jumbo-herstelstatus bevat ongeldige wachtrijgegevens")
            if _queue_completed(conn, household_id, queue_ids):
                pending = None
                cleared = True
        first = min(first, pending) if pending else first
        conn.execute(text("""
            INSERT INTO household_jumbo_import_runs
                (household_id,run_id,pending_from_date,scan_complete,queue_ids)
            VALUES (:household_id,:run_id,:first,false,'[]')
            ON CONFLICT (household_id) DO UPDATE SET
                run_id=EXCLUDED.run_id,
                pending_from_date=CASE WHEN :cleared THEN EXCLUDED.pending_from_date
                ELSE LEAST(household_jumbo_import_runs.pending_from_date,
                           EXCLUDED.pending_from_date) END,
                scan_complete=false,queue_ids='[]',
                updated_at=CURRENT_TIMESTAMP
        """), {"household_id": household_id, "run_id": run_id, "first": first, "cleared": cleared})
        # A concurrent initial begin may have an older checkpoint: return the
        # exact persisted lower bound, never a more recent speculative date.
        first = conn.execute(text("""
            SELECT pending_from_date FROM household_jumbo_import_runs
            WHERE household_id=:household_id
        """), {"household_id": household_id}).scalar_one()
    return {"run_id": run_id, "from_date": first.isoformat(),
            "to_date": today.isoformat(), "scan_complete": False}


def complete_jumbo_history(
    engine: Engine, household_id: str, *, run_id: str, queue_ids: list[str],
) -> dict:
    """Record full scan only after every batch was staged and ACKed.

    A staged or review-required receipt never counts as processed; until all
    queue statuses are completed, the next scan retains the inclusive start.
    """
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Jumbo-historie vereist duurzame PostgreSQL-opslag")
    try:
        if str(UUID(run_id)) != run_id:
            raise ValueError("Ongeldige Jumbo-runidentiteit")
        ids = [str(UUID(value)) for value in queue_ids]
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Ongeldige Jumbo-wachtrijidentiteit") from exc
    if len(ids) != len(set(ids)) or len(ids) > MAX_HISTORY_RECEIPTS:
        raise ValueError("Dubbele of te veel Jumbo-wachtrijidentiteiten")
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT run_id FROM household_jumbo_import_runs
            WHERE household_id=:household_id FOR UPDATE
        """), {"household_id": household_id}).mappings().first()
        if not row or row["run_id"] != run_id:
            raise ValueError("Jumbo-run is verlopen of overgenomen; begin de import opnieuw")
        if ids:
            staged = conn.execute(text("""
                SELECT id,status FROM retailer_import_queue
                WHERE household_id=:household_id AND provider='jumbo'
                  AND id IN :queue_ids
            """).bindparams(bindparam("queue_ids", expanding=True)),
                {"household_id": household_id, "queue_ids": ids},
            ).mappings().all()
            if len(staged) != len(ids) or any(
                entry["status"] not in {"pending", "processing", "completed", "review_required"}
                for entry in staged
            ):
                raise ValueError("Niet alle Jumbo-bonnen zijn voor dit huishouden veilig ontvangen")
        completed = _queue_completed(conn, household_id, ids)
        conn.execute(text("""
            UPDATE household_jumbo_import_runs
            SET scan_complete=true,queue_ids=CAST(:queue_ids AS json),updated_at=CURRENT_TIMESTAMP
            WHERE household_id=:household_id AND run_id=:run_id
        """), {"household_id": household_id, "run_id": run_id,
               "queue_ids": json.dumps(ids)})
    return {"scan_complete": True, "queue_completed": completed,
            "staged_receipts": len(ids),
            "message": "De geschiedenis is gecontroleerd; ontvangen bonnen worden in Kassa verwerkt."}
