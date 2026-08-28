"""Validate migration-owned receipt lifecycle schema authority.

Revision ID: 20260828_02
Revises: 20260828_01
Create Date: 2026-08-28

The canonical receipt lifecycle columns, indexes and explicit-approval trigger
already exist in the immutable SQLite baseline and were ported to PostgreSQL by
20260827_02. This revision deliberately performs no schema mutation: it validates
the existing contract fail-closed before Alembic may advance the revision.
"""

from __future__ import annotations

import gzip
import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260828_02"
down_revision: Union[str, None] = "20260828_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BASELINE_PATH = Path(__file__).resolve().parents[1] / "baseline_sqlite.sql.gz"
_BASELINE_SHA256 = "e75cb2c16e41cd69fa42d2ffdf98dad7f3af67147ed07289edc9caa6ad4fc8b7"
_RECEIPT_TABLES = ("raw_receipts", "receipt_tables", "receipt_table_lines")
_APPROVAL_TRIGGER = "trg_receipt_tables_preserve_explicit_approval"


def _baseline_sql() -> str:
    with gzip.open(_BASELINE_PATH, "rt", encoding="utf-8") as handle:
        baseline = handle.read()
    actual = hashlib.sha256(baseline.encode("utf-8")).hexdigest()
    if actual != _BASELINE_SHA256:
        raise RuntimeError(
            "Immutable SQLite baseline hash mismatch: "
            f"expected={_BASELINE_SHA256} actual={actual}"
        )
    return baseline


def _source_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(_baseline_sql())
    return connection


def _normalize_sql(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _sqlite_columns(connection: Any, table_name: str) -> tuple[tuple[Any, ...], ...]:
    quoted = table_name.replace('"', '""')
    rows = connection.execute(f'PRAGMA table_info("{quoted}")').fetchall()
    return tuple(
        (
            str(row[1]),
            str(row[2] or "").upper(),
            int(row[3] or 0),
            None if row[4] is None else _normalize_sql(row[4]),
            int(row[5] or 0),
        )
        for row in rows
    )


def _sqlite_explicit_objects(
    connection: Any,
    *,
    object_type: str,
) -> dict[str, tuple[str, str]]:
    placeholders = ",".join("?" for _ in _RECEIPT_TABLES)
    rows = connection.execute(
        f"SELECT name, tbl_name, sql FROM sqlite_master "
        f"WHERE type=? AND tbl_name IN ({placeholders}) AND sql IS NOT NULL "
        f"ORDER BY name",
        (object_type, *_RECEIPT_TABLES),
    ).fetchall()
    return {
        str(row[0]): (str(row[1]), _normalize_sql(row[2]))
        for row in rows
    }


def _sqlite_target_columns(bind: sa.engine.Connection, table_name: str) -> tuple[tuple[Any, ...], ...]:
    quoted = table_name.replace('"', '""')
    rows = bind.exec_driver_sql(f'PRAGMA table_info("{quoted}")').fetchall()
    return tuple(
        (
            str(row[1]),
            str(row[2] or "").upper(),
            int(row[3] or 0),
            None if row[4] is None else _normalize_sql(row[4]),
            int(row[5] or 0),
        )
        for row in rows
    )


def _sqlite_target_objects(
    bind: sa.engine.Connection,
    *,
    object_type: str,
) -> dict[str, tuple[str, str]]:
    placeholders = ",".join("?" for _ in _RECEIPT_TABLES)
    rows = bind.exec_driver_sql(
        f"SELECT name, tbl_name, sql FROM sqlite_master "
        f"WHERE type=? AND tbl_name IN ({placeholders}) AND sql IS NOT NULL "
        f"ORDER BY name",
        (object_type, *_RECEIPT_TABLES),
    ).fetchall()
    return {
        str(row[0]): (str(row[1]), _normalize_sql(row[2]))
        for row in rows
    }


def _validate_sqlite(bind: sa.engine.Connection) -> None:
    source = _source_connection()
    try:
        for table_name in _RECEIPT_TABLES:
            expected = _sqlite_columns(source, table_name)
            actual = _sqlite_target_columns(bind, table_name)
            if actual != expected:
                raise RuntimeError(
                    f"Receipt lifecycle SQLite column drift: table={table_name} "
                    f"expected={expected!r} actual={actual!r}"
                )

        expected_indexes = _sqlite_explicit_objects(source, object_type="index")
        actual_indexes = _sqlite_target_objects(bind, object_type="index")
        if actual_indexes != expected_indexes:
            raise RuntimeError(
                "Receipt lifecycle SQLite index drift: "
                f"expected={sorted(expected_indexes)} actual={sorted(actual_indexes)}"
            )
        for index_name, expected in expected_indexes.items():
            if actual_indexes.get(index_name) != expected:
                raise RuntimeError(f"Receipt lifecycle SQLite index SQL drift: {index_name}")

        expected_triggers = _sqlite_explicit_objects(source, object_type="trigger")
        actual_triggers = _sqlite_target_objects(bind, object_type="trigger")
        if expected_triggers != actual_triggers:
            raise RuntimeError(
                "Receipt lifecycle SQLite trigger drift: "
                f"expected={sorted(expected_triggers)} actual={sorted(actual_triggers)}"
            )
        if _APPROVAL_TRIGGER not in expected_triggers:
            raise RuntimeError("Immutable baseline misses receipt approval guard trigger")
    finally:
        source.close()


def _source_index_contract(source: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    contract: dict[str, dict[str, Any]] = {}
    indexes = _sqlite_explicit_objects(source, object_type="index")
    for index_name, (table_name, sql) in indexes.items():
        quoted = index_name.replace('"', '""')
        columns = tuple(
            str(row[2])
            for row in source.execute(f'PRAGMA index_info("{quoted}")').fetchall()
        )
        contract[index_name] = {
            "table": table_name,
            "columns": columns,
            "unique": bool(re.match(r"create\s+unique\s+index\b", sql)),
            "partial": " where " in f" {sql} ",
        }
    return contract


def _validate_postgresql(bind: sa.engine.Connection) -> None:
    source = _source_connection()
    try:
        inspector = sa.inspect(bind)
        actual_tables = set(inspector.get_table_names())
        missing_tables = set(_RECEIPT_TABLES) - actual_tables
        if missing_tables:
            raise RuntimeError(
                f"PostgreSQL receipt lifecycle tables missing: {sorted(missing_tables)}"
            )

        for table_name in _RECEIPT_TABLES:
            source_columns = _sqlite_columns(source, table_name)
            actual_columns = inspector.get_columns(table_name)
            expected_names = tuple(item[0] for item in source_columns)
            actual_names = tuple(str(item.get("name") or "") for item in actual_columns)
            if actual_names != expected_names:
                raise RuntimeError(
                    f"PostgreSQL receipt column drift: table={table_name} "
                    f"expected={expected_names!r} actual={actual_names!r}"
                )
            expected_nullable = {
                item[0]: not bool(item[2]) and not bool(item[4])
                for item in source_columns
            }
            for column in actual_columns:
                name = str(column.get("name") or "")
                if bool(column.get("nullable")) != expected_nullable[name]:
                    raise RuntimeError(
                        f"PostgreSQL receipt nullability drift: {table_name}.{name}"
                    )

        receipt_columns = {
            str(item["name"]): item
            for item in inspector.get_columns("receipt_tables")
        }
        source_receipt_columns = {
            item[0]: item
            for item in _sqlite_columns(source, "receipt_tables")
        }
        workflow_source_default = source_receipt_columns["workflow_state"][3]
        workflow_default = _normalize_sql(receipt_columns["workflow_state"].get("default"))
        if workflow_source_default is None:
            if workflow_default:
                raise RuntimeError(
                    "PostgreSQL receipt_tables.workflow_state unexpectedly gained a server default"
                )
        else:
            expected_workflow_default = str(workflow_source_default).strip("'\"")
            if expected_workflow_default not in workflow_default:
                raise RuntimeError(
                    "PostgreSQL receipt_tables.workflow_state server default drift: "
                    f"expected={workflow_source_default!r} actual={workflow_default!r}"
                )
        if not bool(receipt_columns["logical_receipt_key"].get("nullable")):
            raise RuntimeError("receipt_tables.logical_receipt_key must remain nullable")
        line_columns = {
            str(item["name"]): item
            for item in inspector.get_columns("receipt_table_lines")
        }
        if not bool(line_columns["logical_line_key"].get("nullable")):
            raise RuntimeError("receipt_table_lines.logical_line_key must remain nullable")

        expected_indexes = _source_index_contract(source)
        actual_indexes: dict[str, tuple[str, dict[str, Any]]] = {}
        for table_name in _RECEIPT_TABLES:
            for index in inspector.get_indexes(table_name):
                name = str(index.get("name") or "")
                actual_indexes[name] = (table_name, index)
        if set(actual_indexes) != set(expected_indexes):
            raise RuntimeError(
                "PostgreSQL receipt lifecycle index drift: "
                f"expected={sorted(expected_indexes)} actual={sorted(actual_indexes)}"
            )
        for index_name, expected in expected_indexes.items():
            table_name, actual = actual_indexes[index_name]
            if table_name != expected["table"]:
                raise RuntimeError(f"PostgreSQL receipt index table drift: {index_name}")
            if tuple(actual.get("column_names") or ()) != expected["columns"]:
                raise RuntimeError(f"PostgreSQL receipt index column drift: {index_name}")
            if bool(actual.get("unique")) != expected["unique"]:
                raise RuntimeError(f"PostgreSQL receipt index uniqueness drift: {index_name}")
            where = _normalize_sql(
                (actual.get("dialect_options") or {}).get("postgresql_where")
            )
            if expected["partial"] and not where:
                raise RuntimeError(f"PostgreSQL receipt partial index predicate missing: {index_name}")
            if not expected["partial"] and where:
                raise RuntimeError(f"Unexpected PostgreSQL receipt partial index predicate: {index_name}")

        trigger_rows = bind.execute(
            sa.text(
                """
                SELECT t.tgname, pg_get_triggerdef(t.oid), pg_get_functiondef(t.tgfoid)
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema()
                  AND c.relname = 'receipt_tables'
                  AND NOT t.tgisinternal
                ORDER BY t.tgname
                """
            )
        ).all()
        trigger_names = {str(row[0]) for row in trigger_rows}
        if trigger_names != {_APPROVAL_TRIGGER}:
            raise RuntimeError(
                "PostgreSQL receipt trigger drift: "
                f"expected={[_APPROVAL_TRIGGER]!r} actual={sorted(trigger_names)!r}"
            )
        trigger_def = _normalize_sql(trigger_rows[0][1])
        function_def = _normalize_sql(trigger_rows[0][2])
        for fragment in (
            "before update of parse_status, approved_at on receipt_tables",
            "rezzerv_preserve_explicit_receipt_approval()",
        ):
            if fragment not in trigger_def:
                raise RuntimeError(
                    f"PostgreSQL receipt approval trigger definition drift: missing={fragment!r}"
                )
        for fragment in (
            "new.approved_at is not null",
            "approved_override",
            "returned_to_kassa",
            "removed_reimport_allowed",
            "from raw_receipts",
            "new.updated_at := current_timestamp",
        ):
            if fragment not in function_def:
                raise RuntimeError(
                    f"PostgreSQL receipt approval function drift: missing={fragment!r}"
                )
    finally:
        source.close()


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _validate_sqlite(bind)
        return
    if bind.dialect.name == "postgresql":
        _validate_postgresql(bind)
        return
    raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")


def downgrade() -> None:
    raise RuntimeError(
        "The receipt lifecycle schema-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
