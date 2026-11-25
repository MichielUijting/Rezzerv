"""Server-confirmed, household-scoped browser import runs for Lidl.

A client completion message alone never authorizes store-onboarding success.
The exact run/period and every receipt's durable queue identity must first
be confirmed by the authenticated server. Zero is a valid *completed scan*,
not proof of a persistent Lidl account connection.
"""
from __future__ import annotations

import json
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

from app.services.lidl_import_window_service import get_window
from app.services.retailer_receipt_import_dates import latest_retailer_import_dates

SETTING_KEY = "lidl_browser_import_run_v1"
MAX_RECEIPTS = 2000


def _uuid(value: str) -> str:
    try:
        checked = str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Ongeldige Lidl-importidentiteit") from exc
    if checked != value:
        raise ValueError("Ongeldige Lidl-importidentiteit")
    return checked


def _queue_completed(conn, household_id: str, queue_ids: list[str]) -> bool:
    if not queue_ids:
        return True
    rows = conn.execute(text("""
        SELECT id,status FROM retailer_import_queue
        WHERE household_id=:household_id AND provider='lidl'
          AND id IN :queue_ids
    """).bindparams(bindparam("queue_ids", expanding=True)),
        {"household_id": household_id, "queue_ids": queue_ids},
    ).mappings().all()
    return len(rows) == len(queue_ids) and all(
        row["status"] == "completed" for row in rows
    )


def begin_lidl_browser_import(engine: Engine, household_id: str) -> dict:
    """Preserve the oldest unfinished scan, and never advance past staged receipts."""
    if engine.dialect.name != "postgresql" or not household_id or household_id == "0":
        raise ValueError("Regulier huishouden met PostgreSQL vereist")
    period = get_window(engine, household_id, force_automatic=True)
    start, end = date.fromisoformat(period["from_date"]), date.fromisoformat(period["to_date"])
    latest = latest_retailer_import_dates(engine, household_id=household_id)["lidl"]
    if latest:
        # A processed, recognized purchase is stronger than a browser date.
        # If an old checkpoint is ahead, retain the older confirmed date.
        completed_date = date.fromisoformat(latest)
        old_checkpoint = date.fromisoformat(period["last_imported_date"]) if period.get("last_imported_date") else None
        start = min(completed_date, old_checkpoint) if old_checkpoint and old_checkpoint > completed_date else completed_date
    if start > end:
        raise ValueError("Ongeldige Lidl-importperiode")
    run_id = str(uuid4())
    with engine.begin() as conn:
        raw = conn.execute(text("""
            SELECT setting_value FROM household_settings
            WHERE household_id=:household_id AND setting_key=:key FOR UPDATE
        """), {"household_id": household_id, "key": SETTING_KEY}).scalar_one_or_none()
        try:
            previous = json.loads(raw) if raw else None
        except (ValueError, TypeError) as exc:
            raise ValueError("Lidl-herstelstatus is niet betrouwbaar") from exc
        if previous is not None:
            if not isinstance(previous, dict):
                raise ValueError("Lidl-herstelstatus is niet betrouwbaar")
            earlier = previous.get("from_date")
            ids = previous.get("queue_ids")
            if not isinstance(earlier, str) or not isinstance(ids, list) or len(ids) > MAX_RECEIPTS:
                raise ValueError("Lidl-herstelstatus is onvolledig")
            try:
                earlier_date = date.fromisoformat(earlier)
                ids = [_uuid(value) for value in ids]
            except ValueError as exc:
                raise ValueError("Lidl-herstelstatus bevat ongeldige gegevens") from exc
            if len(set(ids)) != len(ids):
                raise ValueError("Lidl-herstelstatus bevat dubbele bonidentiteiten")
            if not previous.get("scan_complete") or not _queue_completed(conn, household_id, ids):
                start = min(start, earlier_date)
        state = {"run_id": run_id, "from_date": start.isoformat(),
                 "to_date": end.isoformat(), "scan_complete": False, "queue_ids": []}
        conn.execute(text("""
            INSERT INTO household_settings(id,household_id,setting_key,setting_value,updated_at)
            VALUES (:id,:household_id,:key,:value,CURRENT_TIMESTAMP)
            ON CONFLICT (household_id,setting_key) DO UPDATE SET
                setting_value=EXCLUDED.setting_value,updated_at=CURRENT_TIMESTAMP
        """), {"id": uuid4().hex, "household_id": household_id,
               "key": SETTING_KEY, "value": json.dumps(state)})
    return {"run_id": run_id, "from_date": state["from_date"], "to_date": state["to_date"],
            "scan_complete": False}


def complete_lidl_browser_import(
    engine: Engine, household_id: str, *, run_id: str,
    queue_ids: list[str], from_date: date, to_date: date,
) -> dict:
    if engine.dialect.name != "postgresql" or not household_id or household_id == "0":
        raise ValueError("Regulier huishouden met PostgreSQL vereist")
    _uuid(run_id)
    ids = [_uuid(value) for value in queue_ids]
    if len(ids) != len(set(ids)) or len(ids) > MAX_RECEIPTS:
        raise ValueError("Dubbele of te veel Lidl-bonidentiteiten")
    with engine.begin() as conn:
        raw = conn.execute(text("""
            SELECT setting_value FROM household_settings
            WHERE household_id=:household_id AND setting_key=:key FOR UPDATE
        """), {"household_id": household_id, "key": SETTING_KEY}).scalar_one_or_none()
        try:
            state = json.loads(raw) if raw else None
        except (ValueError, TypeError):
            state = None
        if not isinstance(state, dict) or state.get("run_id") != run_id:
            raise ValueError("Lidl-run is verlopen; probeer de import opnieuw")
        if state.get("scan_complete") or (
            state.get("from_date"), state.get("to_date")
        ) != (from_date.isoformat(), to_date.isoformat()):
            raise ValueError("Lidl-importperiode of status komt niet overeen")
        if ids:
            rows = conn.execute(text("""
                SELECT id,status FROM retailer_import_queue
                WHERE household_id=:household_id AND provider='lidl'
                  AND id IN :queue_ids
            """).bindparams(bindparam("queue_ids", expanding=True)),
                {"household_id": household_id, "queue_ids": ids},
            ).mappings().all()
            if len(rows) != len(ids) or any(row["status"] not in {
                "pending", "processing", "completed", "review_required"
            } for row in rows):
                raise ValueError("Niet alle Lidl-bonnen zijn voor dit huishouden ontvangen")
        state["scan_complete"] = True
        state["queue_ids"] = ids
        conn.execute(text("""
            UPDATE household_settings SET setting_value=:value,updated_at=CURRENT_TIMESTAMP
            WHERE household_id=:household_id AND setting_key=:key
        """), {"household_id": household_id, "key": SETTING_KEY,
               "value": json.dumps(state, sort_keys=True)})
    return {"run_id": run_id, "scan_complete": True, "staged_receipts": len(ids),
            "message": "De volledige Lidl-historie is gecontroleerd; ontvangen bonnen worden afzonderlijk verwerkt."}
