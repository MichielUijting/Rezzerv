from __future__ import annotations

import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine


_CURRENT_ACTOR_USER_ID: ContextVar[str | None] = ContextVar(
    "rezzerv_actor_user_id", default=None
)
_CURRENT_ACTOR_HOUSEHOLD_ID: ContextVar[str | None] = ContextVar(
    "rezzerv_actor_household_id", default=None
)
_ATTRIBUTION_WRITE_GUARD: ContextVar[bool] = ContextVar(
    "rezzerv_actor_attribution_write_guard", default=False
)

TRACKED_TABLES = {
    "receipt_tables": "receipt",
    "purchase_import_batches": "unpack_batch",
    "inventory_events": "inventory_event",
}

_INSERT_RE = re.compile(r"^\s*insert\s+into\s+([\w\"\.]+)", re.IGNORECASE)


def bind_current_actor(user_id: str | None, household_id: str | None) -> None:
    _CURRENT_ACTOR_USER_ID.set(str(user_id or "").strip() or None)
    _CURRENT_ACTOR_HOUSEHOLD_ID.set(str(household_id or "").strip() or None)


def clear_current_actor() -> None:
    _CURRENT_ACTOR_USER_ID.set(None)
    _CURRENT_ACTOR_HOUSEHOLD_ID.set(None)


def current_actor_user_id() -> str | None:
    return _CURRENT_ACTOR_USER_ID.get()


def current_actor_household_id() -> str | None:
    return _CURRENT_ACTOR_HOUSEHOLD_ID.get()


def ensure_actor_attribution_schema(conn: Connection) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS actor_object_attributions (
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            household_id TEXT NOT NULL,
            actor_user_id TEXT NOT NULL,
            attribution_source TEXT NOT NULL DEFAULT 'runtime_session',
            first_attributed_at TEXT NOT NULL,
            last_attributed_at TEXT NOT NULL,
            PRIMARY KEY (object_type, object_id)
        )
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_actor_object_attributions_household_actor
        ON actor_object_attributions (household_id, actor_user_id, object_type)
    """))


def backfill_actor_attributions_from_audit(conn: Connection) -> int:
    """Backfill only when the existing audit log names the exact domain object.

    This deliberately refuses heuristic attribution. Historical rows that cannot
    be tied to an exact object id remain unattributed.
    """
    ensure_actor_attribution_schema(conn)
    audit_exists = conn.execute(text("""
        SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='auth_audit_log'
        LIMIT 1
    """)).first()
    if not audit_exists:
        return 0

    object_type_map = {
        "receipt": "receipt",
        "receipt_table": "receipt",
        "kassabon": "receipt",
        "unpack_batch": "unpack_batch",
        "purchase_import_batch": "unpack_batch",
        "inventory_event": "inventory_event",
        "voorraadmutatie": "inventory_event",
    }
    inserted = 0
    for source_type, target_type in object_type_map.items():
        result = conn.execute(text("""
            INSERT INTO actor_object_attributions (
                object_type, object_id, household_id, actor_user_id,
                attribution_source, first_attributed_at, last_attributed_at
            )
            SELECT
                :target_type,
                CAST(object_id AS TEXT),
                CAST(household_id AS TEXT),
                CAST(actor_user_id AS TEXT),
                'auth_audit_log',
                MIN(created_at),
                MAX(created_at)
            FROM auth_audit_log
            WHERE lower(COALESCE(object_type, '')) = :source_type
              AND object_id IS NOT NULL
              AND household_id IS NOT NULL
              AND actor_user_id IS NOT NULL
            GROUP BY object_id, household_id, actor_user_id
            ON CONFLICT(object_type, object_id) DO NOTHING
        """), {"source_type": source_type, "target_type": target_type})
        inserted += max(int(result.rowcount or 0), 0)
    return inserted


def _compiled_parameter_sets(context: Any, parameters: Any) -> list[dict[str, Any]]:
    compiled = getattr(context, "compiled_parameters", None)
    if isinstance(compiled, list):
        return [item for item in compiled if isinstance(item, dict)]
    if isinstance(parameters, dict):
        return [parameters]
    if isinstance(parameters, (list, tuple)) and parameters and isinstance(parameters[0], dict):
        return list(parameters)
    return []


def _normalize_table_name(statement: str) -> str | None:
    match = _INSERT_RE.match(str(statement or ""))
    if not match:
        return None
    raw = match.group(1).replace('"', "")
    return raw.rsplit(".", 1)[-1].lower()


def _extract_object_id(params: dict[str, Any]) -> str | None:
    for key in ("id", "event_id", "batch_id", "receipt_table_id"):
        value = params.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _extract_household_id(params: dict[str, Any]) -> str | None:
    value = params.get("household_id")
    if value not in (None, ""):
        return str(value)
    return current_actor_household_id()


def _record_attribution(
    connection: Connection,
    *,
    object_type: str,
    object_id: str,
    household_id: str,
    actor_user_id: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    guard = _ATTRIBUTION_WRITE_GUARD.set(True)
    try:
        connection.execute(text("""
            INSERT INTO actor_object_attributions (
                object_type, object_id, household_id, actor_user_id,
                attribution_source, first_attributed_at, last_attributed_at
            ) VALUES (
                :object_type, :object_id, :household_id, :actor_user_id,
                'runtime_session', :now, :now
            )
            ON CONFLICT(object_type, object_id) DO UPDATE SET
                household_id = excluded.household_id,
                actor_user_id = excluded.actor_user_id,
                attribution_source = 'runtime_session',
                last_attributed_at = excluded.last_attributed_at
        """), {
            "object_type": object_type,
            "object_id": object_id,
            "household_id": household_id,
            "actor_user_id": actor_user_id,
            "now": now,
        })
    finally:
        _ATTRIBUTION_WRITE_GUARD.reset(guard)


def _after_cursor_execute(
    connection: Connection,
    _cursor,
    statement: str,
    parameters: Any,
    context: Any,
    _executemany: bool,
) -> None:
    if _ATTRIBUTION_WRITE_GUARD.get():
        return
    actor_user_id = current_actor_user_id()
    if not actor_user_id:
        return
    table = _normalize_table_name(statement)
    object_type = TRACKED_TABLES.get(str(table or ""))
    if not object_type:
        return

    for params in _compiled_parameter_sets(context, parameters):
        object_id = _extract_object_id(params)
        household_id = _extract_household_id(params)
        if not object_id or not household_id:
            continue
        _record_attribution(
            connection,
            object_type=object_type,
            object_id=object_id,
            household_id=household_id,
            actor_user_id=actor_user_id,
        )


def install_actor_attribution_tracking(engine: Engine) -> None:
    if getattr(engine, "_rezzerv_actor_attribution_installed", False):
        return
    with engine.begin() as conn:
        ensure_actor_attribution_schema(conn)
        backfill_actor_attributions_from_audit(conn)
    event.listen(engine, "after_cursor_execute", _after_cursor_execute)
    setattr(engine, "_rezzerv_actor_attribution_installed", True)
