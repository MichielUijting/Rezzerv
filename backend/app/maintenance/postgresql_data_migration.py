"""Fail-closed SQLite -> PostgreSQL production-data migration tooling.

The schema is never copied by this module. Both source and target must already
be on the locked Alembic head. The PostgreSQL target schema is created by
Alembic, then this tool replaces data inside one transaction and proves
canonical table-by-table equivalence before commit.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sqlite3
from collections import deque
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.sql.sqltypes import LargeBinary

HEAD_REVISION = "20260830_01"
EXPECTED_APPLICATION_TABLES = 87
BATCH_SIZE = 1000
SYSTEM_TABLES = frozenset({"alembic_version", "sqlite_sequence"})
TARGET_RUNTIME_SENTINELS = (
    "app_users",
    "inventory",
    "receipt_tables",
    "server_sessions",
    "support_threads",
    "household_invitations",
    "receipt_webhook_deliveries",
)
_TRUE_STRINGS = frozenset({"1", "true", "t", "yes", "on"})
_FALSE_STRINGS = frozenset({"0", "false", "f", "no", "off"})


class MigrationError(RuntimeError):
    """Raised whenever a migration precondition or equivalence proof fails."""


def _quote_sqlite_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _application_tables_sqlite(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [
        str(row[0])
        for row in rows
        if str(row[0]) not in SYSTEM_TABLES and not str(row[0]).startswith("sqlite_")
    ]


def _application_tables_postgresql(connection: Connection) -> list[str]:
    return sorted(
        table_name
        for table_name in inspect(connection).get_table_names()
        if table_name not in SYSTEM_TABLES
    )


def _sqlite_revision(connection: sqlite3.Connection) -> str:
    tables = set(_application_tables_sqlite(connection))
    has_version = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
    ).fetchone()
    if not has_version:
        raise MigrationError("SQLite source has no alembic_version table")
    rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
    if len(rows) != 1:
        raise MigrationError(f"SQLite source must have exactly one Alembic revision row; actual={len(rows)}")
    revision = str(rows[0][0] or "").strip()
    if not revision:
        raise MigrationError("SQLite source Alembic revision is empty")
    if not tables:
        raise MigrationError("SQLite source contains no application tables")
    return revision


def _postgresql_revision(connection: Connection) -> str:
    if "alembic_version" not in set(inspect(connection).get_table_names()):
        raise MigrationError("PostgreSQL target has no alembic_version table")
    rows = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    if len(rows) != 1:
        raise MigrationError(
            f"PostgreSQL target must have exactly one Alembic revision row; actual={len(rows)}"
        )
    return str(rows[0] or "").strip()


def _assert_sqlite_integrity(connection: sqlite3.Connection) -> None:
    result = [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]
    if result != ["ok"]:
        raise MigrationError(f"SQLite integrity_check failed: {result!r}")
    foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_rows:
        raise MigrationError(
            "SQLite foreign_key_check failed; first rows=" + repr(foreign_key_rows[:10])
        )


def _sqlite_readonly_connection(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve(strict=True)
    uri = "file:" + quote(resolved.as_posix(), safe="/:\\") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def create_consistent_snapshot(source: Path, output: Path) -> str:
    """Create a SQLite-consistent snapshot via the backup API and return SHA-256."""
    source = source.expanduser().resolve(strict=True)
    output = output.expanduser().resolve()
    if source == output:
        raise MigrationError("Snapshot output must differ from the source database")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)

    with _sqlite_readonly_connection(source) as src:
        _assert_sqlite_integrity(src)
        destination = sqlite3.connect(str(output))
        try:
            src.backup(destination)
            destination.commit()
            _assert_sqlite_integrity(destination)
        finally:
            destination.close()

    return hashlib.sha256(output.read_bytes()).hexdigest()


def _coerce_boolean(value: Any, *, label: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, Decimal) and value in {Decimal(0), Decimal(1)}:
        return bool(int(value))
    normalized = str(value).strip().lower()
    if normalized in _TRUE_STRINGS:
        return True
    if normalized in _FALSE_STRINGS:
        return False
    raise MigrationError(f"{label} contains an invalid legacy Boolean value: {value!r}")


def _parse_datetime(value: Any, *, timezone_aware: bool, label: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    else:
        raw = str(value).strip()
        if not raw:
            raise MigrationError(f"{label} contains an empty datetime value")
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise MigrationError(f"{label} contains an invalid datetime value: {value!r}") from exc
    if timezone_aware:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _coerce_value(value: Any, target_type: sa.types.TypeEngine[Any], *, label: str) -> Any:
    if value is None:
        return None
    if isinstance(target_type, sa.Boolean):
        return _coerce_boolean(value, label=label)
    if isinstance(target_type, sa.DateTime):
        return _parse_datetime(
            value,
            timezone_aware=bool(getattr(target_type, "timezone", False)),
            label=label,
        )
    if isinstance(target_type, sa.Numeric):
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise MigrationError(f"{label} contains an invalid numeric value: {value!r}") from exc
    if isinstance(target_type, sa.Integer):
        if isinstance(value, bool):
            return int(value)
        try:
            converted = int(value)
        except (TypeError, ValueError) as exc:
            raise MigrationError(f"{label} contains an invalid integer value: {value!r}") from exc
        if isinstance(value, float) and value != converted:
            raise MigrationError(f"{label} would lose precision as INTEGER: {value!r}")
        return converted
    if isinstance(target_type, sa.Float):
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise MigrationError(f"{label} contains an invalid floating value: {value!r}") from exc
    if isinstance(target_type, LargeBinary):
        if isinstance(value, memoryview):
            return value.tobytes()
        if isinstance(value, bytearray):
            return bytes(value)
        if isinstance(value, bytes):
            return value
        raise MigrationError(f"{label} contains a non-binary value for a binary target: {type(value).__name__}")
    if isinstance(target_type, (sa.String, sa.Text)):
        return str(value)
    return value


def _canonical_decimal(value: Any, *, label: str) -> str:
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MigrationError(f"{label} cannot be canonicalized as decimal: {value!r}") from exc
    if decimal_value == 0:
        return "0"
    return format(decimal_value.normalize(), "f")


def _canonical_value(value: Any, target_type: sa.types.TypeEngine[Any], *, label: str) -> Any:
    coerced = _coerce_value(value, target_type, label=label)
    if coerced is None:
        return None
    if isinstance(target_type, sa.Boolean):
        return bool(coerced)
    if isinstance(target_type, sa.DateTime):
        dt = coerced
        assert isinstance(dt, datetime)
        if bool(getattr(target_type, "timezone", False)):
            dt = dt.astimezone(timezone.utc)
            return dt.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return dt.isoformat(timespec="microseconds")
    if isinstance(target_type, sa.Date):
        if isinstance(coerced, datetime):
            raise MigrationError(f"{label} contains a datetime value for a date target: {coerced!r}")
        if isinstance(coerced, date):
            return coerced.isoformat()
        raw = str(coerced).strip()
        if not raw:
            raise MigrationError(f"{label} contains an empty date value")
        try:
            return date.fromisoformat(raw).isoformat()
        except ValueError as exc:
            raise MigrationError(f"{label} contains an invalid date value: {value!r}") from exc
    if isinstance(target_type, sa.Numeric):
        return _canonical_decimal(coerced, label=label)
    if isinstance(target_type, LargeBinary):
        return {"base64": base64.b64encode(bytes(coerced)).decode("ascii")}
    if isinstance(target_type, sa.Integer):
        return int(coerced)
    if isinstance(target_type, sa.Float):
        return repr(float(coerced))
    if isinstance(coerced, bytes):
        return {"base64": base64.b64encode(coerced).decode("ascii")}
    return coerced


def _row_digest(
    row: Mapping[str, Any],
    columns: Sequence[sa.Column[Any]],
    *,
    table_name: str,
) -> str:
    canonical = [
        _canonical_value(row[column.name], column.type, label=f"{table_name}.{column.name}")
        for column in columns
    ]
    payload = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _digest_multiset(digests: Iterable[str]) -> str:
    hasher = hashlib.sha256()
    for digest in sorted(digests):
        hasher.update(digest.encode("ascii"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def _sqlite_column_names(connection: sqlite3.Connection, table_name: str) -> list[str]:
    quoted = _quote_sqlite_identifier(table_name)
    return [str(row[1]) for row in connection.execute(f"PRAGMA table_info({quoted})").fetchall()]


def _sqlite_rows(
    connection: sqlite3.Connection,
    table_name: str,
    columns: Sequence[str],
) -> list[sqlite3.Row]:
    select_columns = ", ".join(_quote_sqlite_identifier(name) for name in columns)
    quoted_table = _quote_sqlite_identifier(table_name)
    return list(connection.execute(f"SELECT {select_columns} FROM {quoted_table}").fetchall())


def _table_dependencies(connection: Connection, tables: Sequence[str]) -> dict[str, set[str]]:
    table_set = set(tables)
    inspector = inspect(connection)
    dependencies: dict[str, set[str]] = {table: set() for table in tables}
    for table in tables:
        for fk in inspector.get_foreign_keys(table):
            referred = str(fk.get("referred_table") or "")
            if referred in table_set and referred != table:
                dependencies[table].add(referred)
    return dependencies


def _topological_table_order(dependencies: Mapping[str, set[str]]) -> list[str]:
    remaining = {name: set(values) for name, values in dependencies.items()}
    ready = deque(sorted(name for name, values in remaining.items() if not values))
    ordered: list[str] = []
    while ready:
        current = ready.popleft()
        if current in ordered:
            continue
        ordered.append(current)
        for name in sorted(remaining):
            if current in remaining[name]:
                remaining[name].remove(current)
                if not remaining[name] and name not in ordered and name not in ready:
                    ready.append(name)
    if len(ordered) != len(remaining):
        blocked = {name: sorted(values) for name, values in remaining.items() if values}
        raise MigrationError(f"Cross-table foreign-key cycle detected: {blocked!r}")
    return ordered


def _order_self_referential_rows(
    rows: Sequence[Mapping[str, Any]],
    self_fks: Sequence[Mapping[str, Any]],
    *,
    table_name: str,
) -> list[Mapping[str, Any]]:
    if not rows or not self_fks:
        return list(rows)
    dependencies: dict[int, set[int]] = {index: set() for index in range(len(rows))}
    for fk in self_fks:
        local_columns = tuple(str(value) for value in (fk.get("constrained_columns") or ()))
        remote_columns = tuple(str(value) for value in (fk.get("referred_columns") or ()))
        if not local_columns or len(local_columns) != len(remote_columns):
            raise MigrationError(f"Unsupported self foreign key in {table_name}: {fk!r}")
        remote_lookup: dict[tuple[Any, ...], int] = {}
        for index, row in enumerate(rows):
            remote_lookup[tuple(row[column] for column in remote_columns)] = index
        for index, row in enumerate(rows):
            local_key = tuple(row[column] for column in local_columns)
            if any(value is None for value in local_key):
                continue
            dependency = remote_lookup.get(local_key)
            if dependency is not None and dependency != index:
                dependencies[index].add(dependency)
    ordered_indexes = _topological_table_order(
        {str(index): {str(value) for value in values} for index, values in dependencies.items()}
    )
    return [rows[int(index)] for index in ordered_indexes]


def _normalize_row(row: Mapping[str, Any], target_table: sa.Table) -> dict[str, Any]:
    return {
        column.name: _coerce_value(
            row[column.name], column.type, label=f"{target_table.name}.{column.name}"
        )
        for column in target_table.columns
    }


def _assert_matching_table_contract(
    source: sqlite3.Connection,
    target: Connection,
) -> list[str]:
    source_tables = sorted(_application_tables_sqlite(source))
    target_tables = _application_tables_postgresql(target)
    if source_tables != target_tables:
        raise MigrationError(
            "Source/target application table sets differ: "
            f"missing_target={sorted(set(source_tables) - set(target_tables))!r} "
            f"missing_source={sorted(set(target_tables) - set(source_tables))!r}"
        )
    if len(source_tables) != EXPECTED_APPLICATION_TABLES:
        raise MigrationError(
            f"Expected {EXPECTED_APPLICATION_TABLES} application tables at {HEAD_REVISION}; "
            f"actual={len(source_tables)}"
        )
    target_inspector = inspect(target)
    for table_name in source_tables:
        source_columns = _sqlite_column_names(source, table_name)
        target_columns = [str(item["name"]) for item in target_inspector.get_columns(table_name)]
        if set(source_columns) != set(target_columns):
            raise MigrationError(
                f"Column set differs for {table_name}: "
                f"source_only={sorted(set(source_columns) - set(target_columns))!r} "
                f"target_only={sorted(set(target_columns) - set(source_columns))!r}"
            )
    return source_tables


def _assert_target_safe_to_reset(connection: Connection) -> None:
    tables = set(_application_tables_postgresql(connection))
    for table_name in TARGET_RUNTIME_SENTINELS:
        if table_name not in tables:
            raise MigrationError(f"Fresh-target sentinel table is missing: {table_name}")
        quoted = connection.dialect.identifier_preparer.quote(table_name)
        count = int(connection.execute(text(f"SELECT COUNT(*) FROM {quoted}")).scalar_one())
        if count:
            raise MigrationError(
                f"Target is not a fresh migration target: sentinel {table_name} contains {count} rows"
            )


def _truncate_target(connection: Connection, tables: Sequence[str]) -> None:
    quoted = ", ".join(connection.dialect.identifier_preparer.quote(name) for name in tables)
    connection.exec_driver_sql(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")


def _self_foreign_keys(connection: Connection, table_name: str) -> list[Mapping[str, Any]]:
    return [
        fk
        for fk in inspect(connection).get_foreign_keys(table_name)
        if str(fk.get("referred_table") or "") == table_name
    ]


def _load_table(
    source: sqlite3.Connection,
    target: Connection,
    table_name: str,
) -> int:
    metadata = sa.MetaData()
    target_table = sa.Table(table_name, metadata, autoload_with=target)
    column_names = [column.name for column in target_table.columns]
    source_rows = _sqlite_rows(source, table_name, column_names)
    rows: Sequence[Mapping[str, Any]] = [dict(row) for row in source_rows]
    self_fks = _self_foreign_keys(target, table_name)
    if self_fks:
        rows = _order_self_referential_rows(rows, self_fks, table_name=table_name)
    for offset in range(0, len(rows), BATCH_SIZE):
        batch = [_normalize_row(row, target_table) for row in rows[offset : offset + BATCH_SIZE]]
        if batch:
            target.execute(target_table.insert(), batch)
    return len(rows)


def _repair_postgresql_sequences(connection: Connection, tables: Sequence[str]) -> int:
    inspector = inspect(connection)
    repaired = 0
    for table_name in tables:
        quoted_table = connection.dialect.identifier_preparer.quote(table_name)
        for column in inspector.get_columns(table_name):
            column_name = str(column.get("name") or "")
            if not isinstance(column.get("type"), sa.Integer):
                continue
            sequence_name = connection.execute(
                text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                {"table_name": table_name, "column_name": column_name},
            ).scalar_one_or_none()
            if not sequence_name:
                continue
            quoted_column = connection.dialect.identifier_preparer.quote(column_name)
            maximum = connection.execute(
                text(f"SELECT MAX({quoted_column}) FROM {quoted_table}")
            ).scalar_one()
            if maximum is None:
                connection.execute(
                    text("SELECT setval(CAST(:sequence_name AS regclass), 1, false)"),
                    {"sequence_name": str(sequence_name)},
                )
            else:
                connection.execute(
                    text("SELECT setval(CAST(:sequence_name AS regclass), :value, true)"),
                    {"sequence_name": str(sequence_name), "value": int(maximum)},
                )
            repaired += 1
    return repaired


def _table_manifest(
    source: sqlite3.Connection,
    target: Connection,
    table_name: str,
) -> dict[str, Any]:
    metadata = sa.MetaData()
    target_table = sa.Table(table_name, metadata, autoload_with=target)
    columns = list(target_table.columns)
    column_names = [column.name for column in columns]
    source_rows = [dict(row) for row in _sqlite_rows(source, table_name, column_names)]
    quoted_table = target.dialect.identifier_preparer.quote(table_name)
    target_rows = [
        dict(row)
        for row in target.execute(
            text(
                "SELECT "
                + ", ".join(target.dialect.identifier_preparer.quote(name) for name in column_names)
                + f" FROM {quoted_table}"
            )
        ).mappings()
    ]
    source_digests = [_row_digest(row, columns, table_name=table_name) for row in source_rows]
    target_digests = [_row_digest(row, columns, table_name=table_name) for row in target_rows]
    primary_key_names = [column.name for column in target_table.primary_key.columns]
    pk_columns = [target_table.columns[name] for name in primary_key_names]
    source_pk_digests = [
        _row_digest(row, pk_columns, table_name=table_name) for row in source_rows
    ] if pk_columns else []
    target_pk_digests = [
        _row_digest(row, pk_columns, table_name=table_name) for row in target_rows
    ] if pk_columns else []
    manifest = {
        "table": table_name,
        "source_rows": len(source_rows),
        "target_rows": len(target_rows),
        "source_sha256": _digest_multiset(source_digests),
        "target_sha256": _digest_multiset(target_digests),
        "primary_key": primary_key_names,
        "source_pk_sha256": _digest_multiset(source_pk_digests) if pk_columns else None,
        "target_pk_sha256": _digest_multiset(target_pk_digests) if pk_columns else None,
    }
    if manifest["source_rows"] != manifest["target_rows"]:
        raise MigrationError(f"Row-count mismatch for {table_name}: {manifest!r}")
    if manifest["source_sha256"] != manifest["target_sha256"]:
        raise MigrationError(f"Canonical content mismatch for {table_name}: {manifest!r}")
    if pk_columns and manifest["source_pk_sha256"] != manifest["target_pk_sha256"]:
        raise MigrationError(f"Primary-key mismatch for {table_name}: {manifest!r}")
    return manifest


def _engine_for_target(raw_url: str) -> Engine:
    if not raw_url.strip():
        raise MigrationError("MIGRATION_DATABASE_URL/--target-url is required")
    url = make_url(raw_url.strip())
    if url.get_backend_name() != "postgresql":
        raise MigrationError(
            f"Data migration target must be PostgreSQL; actual={url.get_backend_name()!r}"
        )
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return create_engine(url, poolclass=sa.pool.NullPool)


def migrate_head_to_head(
    source_path: Path,
    target_url: str,
    *,
    allow_target_reset: bool,
) -> dict[str, Any]:
    if not allow_target_reset:
        raise MigrationError("Refusing target data replacement without --allow-target-reset")
    source_path = source_path.expanduser().resolve(strict=True)
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    target_engine = _engine_for_target(target_url)
    try:
        with _sqlite_readonly_connection(source_path) as source:
            _assert_sqlite_integrity(source)
            source_revision = _sqlite_revision(source)
            if source_revision != HEAD_REVISION:
                raise MigrationError(
                    f"SQLite source must be at {HEAD_REVISION}; actual={source_revision!r}. "
                    "Upgrade only a working copy of the immutable snapshot before importing."
                )
            with target_engine.begin() as target:
                target_revision = _postgresql_revision(target)
                if target_revision != HEAD_REVISION:
                    raise MigrationError(
                        f"PostgreSQL target must be at {HEAD_REVISION}; actual={target_revision!r}"
                    )
                tables = _assert_matching_table_contract(source, target)
                _assert_target_safe_to_reset(target)
                load_order = _topological_table_order(_table_dependencies(target, tables))
                _truncate_target(target, tables)
                loaded_rows = {table: _load_table(source, target, table) for table in load_order}
                repaired_sequences = _repair_postgresql_sequences(target, tables)
                manifests = [_table_manifest(source, target, table) for table in tables]
                return {
                    "source_sha256": source_sha256,
                    "source_revision": source_revision,
                    "target_revision": target_revision,
                    "application_tables": len(tables),
                    "loaded_rows": sum(loaded_rows.values()),
                    "repaired_sequences": repaired_sequences,
                    "tables": manifests,
                }
    finally:
        target_engine.dispose()


def _write_report(report: Mapping[str, Any], path: str | None) -> None:
    if not path:
        return
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot", help="Create a SQLite-consistent immutable snapshot")
    snapshot.add_argument("--source", required=True, type=Path)
    snapshot.add_argument("--output", required=True, type=Path)
    migrate = subparsers.add_parser("migrate", help="Copy data from SQLite head into PostgreSQL head")
    migrate.add_argument("--source", required=True, type=Path)
    migrate.add_argument(
        "--target-url",
        default=str(os.getenv("MIGRATION_DATABASE_URL") or ""),
        help="Privileged PostgreSQL migration URL; defaults to MIGRATION_DATABASE_URL",
    )
    migrate.add_argument("--allow-target-reset", action="store_true")
    migrate.add_argument("--report-json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "snapshot":
        digest = create_consistent_snapshot(args.source, args.output)
        print(f"POSTGRESQL_DATA_MIGRATION_SNAPSHOT_GREEN sha256={digest}")
        return 0
    report = migrate_head_to_head(
        args.source,
        args.target_url,
        allow_target_reset=bool(args.allow_target_reset),
    )
    _write_report(report, args.report_json)
    print(f"POSTGRESQL_DATA_MIGRATION_HEAD_GREEN revision={HEAD_REVISION}")
    print(f"POSTGRESQL_DATA_MIGRATION_TABLE_SET_GREEN tables={report['application_tables']}")
    print(f"POSTGRESQL_DATA_MIGRATION_SEQUENCES_GREEN repaired={report['repaired_sequences']}")
    print(
        "POSTGRESQL_DATA_MIGRATION_EQUIVALENCE_GREEN "
        f"tables={report['application_tables']} rows={report['loaded_rows']}"
    )
    print("POSTGRESQL_DATA_MIGRATION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
