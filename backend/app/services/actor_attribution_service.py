from __future__ import annotations

import csv
import io
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import event, inspect, text
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
_INSERT_VALUES_RE = re.compile(
    r"^\s*insert\s+into\s+[\w\"\.]+\s*\((?P<columns>.*?)\)\s*values\s*\((?P<values>.*?)\)",
    re.IGNORECASE | re.DOTALL,
)


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
    """Validate the Alembic-owned actor-attribution schema without runtime DDL."""
    inspector = inspect(conn)
    table_name = "actor_object_attributions"
    if not inspector.has_table(table_name):
        raise RuntimeError(
            "actor_object_attributions ontbreekt; voer eerst Alembic-migraties uit"
        )
    columns = {
        str(column.get("name") or ""): column
        for column in inspector.get_columns(table_name)
    }
    required = {
        "object_type",
        "object_id",
        "household_id",
        "actor_user_id",
        "attribution_source",
        "first_attributed_at",
        "last_attributed_at",
    }
    missing = required - set(columns)
    if missing:
        raise RuntimeError(
            "actor_object_attributions mist canonieke kolommen: "
            + ", ".join(sorted(missing))
        )
    for column_name in required:
        if bool(columns[column_name].get("nullable")):
            raise RuntimeError(
                f"actor_object_attributions.{column_name} moet NOT NULL zijn"
            )
    primary_key = tuple(
        str(column or "")
        for column in (
            inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
        )
    )
    if primary_key != ("object_type", "object_id"):
        raise RuntimeError(
            "actor_object_attributions heeft een onjuiste primaire sleutel: "
            f"{primary_key!r}"
        )
    indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes(table_name)
    }
    index = indexes.get("idx_actor_object_attributions_household_actor")
    expected_columns = ("household_id", "actor_user_id", "object_type")
    actual_columns = tuple((index or {}).get("column_names") or ())
    if not index or actual_columns != expected_columns or bool(index.get("unique")):
        raise RuntimeError(
            "actor_object_attributions indexcontract wijkt af: "
            f"expected={expected_columns!r} actual={actual_columns!r} "
            f"unique={bool((index or {}).get('unique'))}"
        )


def backfill_actor_attributions_from_audit(conn: Connection) -> int:
    """Backfill only when the existing audit log names the exact domain object.

    Historical rows without an exact audited object id deliberately remain
    unattributed; S2 never guesses which household member performed an action.
    """
    ensure_actor_attribution_schema(conn)
    if "auth_audit_log" not in set(inspect(conn).get_table_names()):
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
        useful = [item for item in compiled if isinstance(item, dict) and item]
        if useful:
            return useful
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


def _split_sql_csv(value: str) -> list[str]:
    reader = csv.reader(
        io.StringIO(value),
        delimiter=",",
        quotechar="'",
        skipinitialspace=True,
    )
    try:
        return [part.strip() for part in next(reader)]
    except (StopIteration, csv.Error):
        return []


def _literal_insert_params(statement: str) -> dict[str, Any]:
    """Recover identity fields from simple literal INSERT statements.

    Production writes normally use bound parameters, but diagnostics and
    regression paths may emit literal SQL. Actor attribution must not silently
    disappear merely because the same INSERT was expressed without bind params.
    Only plain VALUES inserts are handled; expressions fall back to the bound
    actor household and are never guessed.
    """
    match = _INSERT_VALUES_RE.match(str(statement or ""))
    if not match:
        return {}
    columns = [part.strip().strip('"').lower() for part in _split_sql_csv(match.group("columns"))]
    values = _split_sql_csv(match.group("values"))
    if not columns or len(columns) != len(values):
        return {}

    recovered: dict[str, Any] = {}
    for column, raw_value in zip(columns, values):
        if column not in {"id", "event_id", "batch_id", "receipt_table_id", "household_id"}:
            continue
        token = raw_value.strip()
        if token.startswith(":") or token == "?" or re.match(r"^\$\d+$", token):
            continue
        if token.upper() == "NULL" or "(" in token or ")" in token:
            continue
        recovered[column] = token.strip("'\"")
    return recovered


def _parameter_sets(context: Any, parameters: Any, statement: str) -> list[dict[str, Any]]:
    bound = _compiled_parameter_sets(context, parameters)
    if bound:
        return bound
    literal = _literal_insert_params(statement)
    return [literal] if literal else []


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


def attribute_current_actor_object(
    connection: Connection,
    *,
    object_type: str,
    object_id: str,
    household_id: str | None = None,
) -> bool:
    """Explicitly attribute a domain object to the actor bound to this request.

    This is the deterministic integration point for domain services that know
    the newly-created object id. The SQL hook remains a compatibility safety net.
    """
    actor_user_id = current_actor_user_id()
    effective_household_id = str(household_id or current_actor_household_id() or "").strip()
    effective_object_id = str(object_id or "").strip()
    if not actor_user_id or not effective_household_id or not effective_object_id:
        return False
    ensure_actor_attribution_schema(connection)
    _record_attribution(
        connection,
        object_type=str(object_type),
        object_id=effective_object_id,
        household_id=effective_household_id,
        actor_user_id=actor_user_id,
    )
    return True


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

    for params in _parameter_sets(context, parameters, statement):
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
