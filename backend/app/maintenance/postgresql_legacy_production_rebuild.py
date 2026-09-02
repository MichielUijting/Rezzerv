"""Fail-closed canonical rebuild for unversioned production SQLite snapshots.

The immutable source is never stamped or upgraded. A fresh canonical SQLite
head is built through the real Alembic history; production rows are overlaid
only after fail-closed schema checks. Known receipt FK drift is the only
recoverable FK anomaly. Migration-owned seed data remains Alembic-owned.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

HEAD_REVISION = "20260902_01"
BASELINE_REVISION = "20260827_01"
EXPECTED_APPLICATION_TABLES = 88
SYSTEM_TABLES = frozenset({"alembic_version", "sqlite_sequence"})
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = BACKEND_ROOT / "alembic.ini"
SQLITE_BASELINE = BACKEND_ROOT / "alembic" / "baseline_sqlite.sql.gz"
RECEIPT_HOUSEHOLD_TABLES = frozenset({"receipt_sources", "raw_receipts", "receipt_tables"})


class LegacyAdoptionError(RuntimeError):
    """Raised when a production snapshot cannot be proven safe to rebuild."""


def _q(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _readonly_connection(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve(strict=True)
    uri = "file:" + quote(resolved.as_posix(), safe="/:\\") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _assert_integrity_only(connection: sqlite3.Connection) -> None:
    rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]
    if rows != ["ok"]:
        raise LegacyAdoptionError(f"SQLite integrity_check failed: {rows!r}")


def _has_table(connection: sqlite3.Connection, table_name: str) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table_name,),
        ).fetchone()
    )


def _application_tables(connection: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        if str(row[0]) not in SYSTEM_TABLES and not str(row[0]).startswith("sqlite_")
    ]


def _schema_dump(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE sql IS NOT NULL
          AND name NOT LIKE 'sqlite_%'
          AND name <> 'alembic_version'
        ORDER BY CASE type
          WHEN 'table' THEN 0 WHEN 'view' THEN 1
          WHEN 'index' THEN 2 WHEN 'trigger' THEN 3 ELSE 4 END, name
        """
    ).fetchall()
    output: list[str] = []
    for object_type, name, table_name, sql in rows:
        statement = str(sql or "").strip().rstrip(";")
        if statement:
            output += [
                f"-- {object_type}: {name} (table={table_name})",
                statement + ";",
                "",
            ]
    return "\n".join(output).rstrip() + "\n"


def _registry_contains(connection: sqlite3.Connection, household_id: Any) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM household_registry WHERE id=? LIMIT 1",
            (str(household_id),),
        ).fetchone()
    )


def _fk_definition(
    connection: sqlite3.Connection, table_name: str, fk_id: int
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    rows = [
        row
        for row in connection.execute(f"PRAGMA foreign_key_list({_q(table_name)})").fetchall()
        if int(row[0]) == int(fk_id)
    ]
    if not rows:
        raise LegacyAdoptionError(
            f"foreign_key_check references unknown FK: table={table_name!r} fk_id={fk_id}"
        )
    rows.sort(key=lambda row: int(row[1]))
    return (
        str(rows[0][2]),
        tuple(str(row[3]) for row in rows),
        tuple(str(row[4]) for row in rows),
    )


def _row_by_rowid(
    connection: sqlite3.Connection, table_name: str, rowid: int
) -> sqlite3.Row:
    row = connection.execute(
        f"SELECT rowid AS __rowid__, * FROM {_q(table_name)} WHERE rowid=?",
        (rowid,),
    ).fetchone()
    if row is None:
        raise LegacyAdoptionError(
            f"foreign_key_check row disappeared: table={table_name!r} rowid={rowid}"
        )
    return row


def classify_known_legacy_fk_drift(connection: sqlite3.Connection) -> dict[str, Any]:
    """Allow only the two receipt drift patterns proven on production."""
    _assert_integrity_only(connection)
    required = {"household_registry", "receipt_sources", "raw_receipts", "receipt_tables"}
    missing = required - set(_application_tables(connection))
    if missing:
        raise LegacyAdoptionError(
            f"Legacy receipt recovery mist vereiste tabellen: {sorted(missing)}"
        )

    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    categories: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []
    for violation in violations:
        table_name, rowid, parent_table, fk_id = (
            str(violation[0]), int(violation[1]), str(violation[2]), int(violation[3])
        )
        parent, local_columns, remote_columns = _fk_definition(
            connection, table_name, fk_id
        )
        if parent != parent_table:
            raise LegacyAdoptionError(
                f"SQLite FK metadata mismatch: check_parent={parent_table!r} "
                f"metadata_parent={parent!r}"
            )
        row = _row_by_rowid(connection, table_name, rowid)

        if (
            table_name in RECEIPT_HOUSEHOLD_TABLES
            and parent_table == "households"
            and local_columns == ("household_id",)
            and remote_columns == ("id",)
        ):
            household_id = str(row["household_id"] or "")
            if not household_id or not _registry_contains(connection, household_id):
                raise LegacyAdoptionError(
                    "Receipt household FK drift wijst niet naar household_registry: "
                    f"table={table_name!r} household_id={household_id!r}"
                )
            category = f"{table_name}.household_id->legacy-households"
        elif (
            table_name == "raw_receipts"
            and parent_table == "receipt_sources"
            and local_columns == ("source_id",)
            and remote_columns == ("id",)
        ):
            household_id = str(row["household_id"] or "")
            source_id = str(row["source_id"] or "")
            if (
                not household_id
                or source_id != f"{household_id}-manual-upload"
                or not _registry_contains(connection, household_id)
            ):
                raise LegacyAdoptionError(
                    "Onbekende ontbrekende receipt source-parent: "
                    f"raw_receipt_id={row['id']!r} household_id={household_id!r} "
                    f"source_id={source_id!r}"
                )
            category = "raw_receipts.source_id->missing-manual-upload"
        else:
            raise LegacyAdoptionError(
                "Onbekende legacy foreign-key drift; adoption geweigerd: "
                f"table={table_name!r} rowid={rowid} parent={parent_table!r} "
                f"local={local_columns!r} remote={remote_columns!r}"
            )

        categories[category] += 1
        if len(samples) < 20:
            samples.append(
                {"table": table_name, "rowid": rowid, "parent": parent_table, "category": category}
            )

    return {
        "violations": len(violations),
        "categories": dict(sorted(categories.items())),
        "samples": samples,
    }


def _sqlite_url(path: Path) -> str:
    return "sqlite:///" + path.resolve().as_posix()


def _run_alembic(path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    url = _sqlite_url(path)
    env.update(
        {
            "DATABASE_URL": url,
            "MIGRATION_DATABASE_URL": url,
            "REZZERV_DATASTORE_POLICY": "compatibility",
            "PYTHONPATH": str(BACKEND_ROOT),
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_CONFIG), *arguments],
        cwd=str(BACKEND_ROOT),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _revision(path: Path) -> str:
    connection = sqlite3.connect(str(path))
    try:
        if not _has_table(connection, "alembic_version"):
            return ""
        rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
    finally:
        connection.close()
    return str(rows[0][0] or "").strip() if len(rows) == 1 else ""


def _build_canonical_head(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with gzip.open(SQLITE_BASELINE, "rt", encoding="utf-8") as handle:
        baseline_sql = handle.read()
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(baseline_sql)
        connection.commit()
    finally:
        connection.close()

    for args in (("stamp", BASELINE_REVISION), ("upgrade", "head")):
        result = _run_alembic(path, *args)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout)[-2000:]
            raise LegacyAdoptionError(f"Canonical Alembic {' '.join(args)} failed: {detail}")

    if _revision(path) != HEAD_REVISION:
        raise LegacyAdoptionError(
            f"Canonical rebuild ended at {_revision(path)!r}; expected {HEAD_REVISION!r}"
        )

    connection = sqlite3.connect(str(path))
    try:
        _assert_integrity_only(connection)
        fk_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        if fk_rows:
            raise LegacyAdoptionError(f"Fresh canonical head has FK violations: {fk_rows[:10]!r}")
        tables = _application_tables(connection)
        if len(tables) != EXPECTED_APPLICATION_TABLES:
            raise LegacyAdoptionError(
                f"Unexpected canonical table count: {len(tables)} "
                f"(expected {EXPECTED_APPLICATION_TABLES})"
            )
        return _schema_dump(connection)
    finally:
        connection.close()


def _columns(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [
        {
            "name": str(row[1]),
            "type": str(row[2] or ""),
            "notnull": int(row[3]),
            "default": row[4],
            "pk": int(row[5]),
        }
        for row in connection.execute(f"PRAGMA table_info({_q(table)})").fetchall()
    ]


def _pk_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        item["name"]
        for item in sorted(
            (item for item in _columns(connection, table) if item["pk"]),
            key=lambda item: item["pk"],
        )
    ]


def _count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {_q(table)}").fetchone()[0])


def _value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, memoryview):
        return {"base64": base64.b64encode(value.tobytes()).decode("ascii")}
    if isinstance(value, float):
        return {"float": repr(value)}
    if isinstance(value, (int, str)):
        return value
    return {"repr": repr(value)}


def _row_digest(row: Sequence[Any]) -> str:
    payload = json.dumps([_value(v) for v in row], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fingerprints(
    connection: sqlite3.Connection, table: str, names: Sequence[str]
) -> Counter[str]:
    if not names:
        return Counter()
    cursor = connection.execute(
        f"SELECT {', '.join(_q(name) for name in names)} FROM {_q(table)}"
    )
    result: Counter[str] = Counter()
    for row in cursor:
        result[_row_digest(tuple(row))] += 1
    return result


def _counter_sha(counter: Counter[str]) -> str:
    hasher = hashlib.sha256()
    for digest, count in sorted(counter.items()):
        for _ in range(count):
            hasher.update((digest + "\n").encode("ascii"))
    return hasher.hexdigest()


def _capture_triggers(connection: sqlite3.Connection) -> list[tuple[str, str]]:
    return [
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='trigger' AND sql IS NOT NULL ORDER BY name"
        ).fetchall()
    ]


def _preflight(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    source_tables: Sequence[str],
) -> tuple[list[str], dict[str, int], dict[str, dict[str, Any]]]:
    target_tables = _application_tables(target)
    source_only = sorted(set(source_tables) - set(target_tables))
    if source_only:
        raise LegacyAdoptionError(
            f"Legacy source bevat niet-canonical tabellen: {source_only!r}"
        )

    canonical_only = sorted(set(target_tables) - set(source_tables))
    canonical_only_counts = {table: _count(target, table) for table in canonical_only}
    mapping: dict[str, dict[str, Any]] = {}

    for table in source_tables:
        if _count(target, table):
            raise LegacyAdoptionError(
                f"Migration-owned rows conflict with legacy source table {table!r}"
            )

        source_columns = _columns(source, table)
        target_columns = _columns(target, table)
        source_names = [item["name"] for item in source_columns]
        target_map = {item["name"]: item for item in target_columns}
        missing = [name for name in source_names if name not in target_map]
        if missing:
            raise LegacyAdoptionError(
                f"Legacy columns ontbreken in canonical {table}: {missing!r}"
            )

        target_only = [item for item in target_columns if item["name"] not in set(source_names)]
        unsafe = [
            item["name"]
            for item in target_only
            if item["notnull"] and item["default"] is None and not item["pk"]
        ]
        if unsafe:
            raise LegacyAdoptionError(
                f"Canonical target vereist verzonnen data voor {table}: {unsafe!r}"
            )

        mapping[table] = {
            "source_rows": _count(source, table),
            "source_columns": source_names,
            "primary_key": _pk_columns(source, table),
            "target_only_columns": [item["name"] for item in target_only],
        }
    return canonical_only, canonical_only_counts, mapping


def _copy_rows(
    source: sqlite3.Connection, target: sqlite3.Connection, source_tables: Sequence[str]
) -> dict[str, int]:
    copied: dict[str, int] = {}
    for table in source_tables:
        names = [item["name"] for item in _columns(source, table)]
        columns = ", ".join(_q(name) for name in names)
        placeholders = ", ".join("?" for _ in names)
        rows = [tuple(row) for row in source.execute(f"SELECT {columns} FROM {_q(table)}")]
        if rows:
            target.executemany(
                f"INSERT INTO {_q(table)} ({columns}) VALUES ({placeholders})", rows
            )
        copied[table] = len(rows)
    return copied


def _repair_receipt_boundary(connection: sqlite3.Connection) -> int:
    for table in RECEIPT_HOUSEHOLD_TABLES:
        row = connection.execute(
            f"""
            SELECT child.household_id
            FROM {_q(table)} AS child
            LEFT JOIN household_registry AS registry ON registry.id=child.household_id
            WHERE child.household_id IS NOT NULL AND registry.id IS NULL
            LIMIT 1
            """
        ).fetchone()
        if row:
            raise LegacyAdoptionError(
                f"{table}.household_id bevat niet-geregistreerde household: {row[0]!r}"
            )

    invalid = connection.execute(
        """
        SELECT raw.id, raw.household_id, raw.source_id
        FROM raw_receipts AS raw
        LEFT JOIN receipt_sources AS source ON source.id=raw.source_id
        WHERE raw.source_id IS NOT NULL AND source.id IS NULL
          AND raw.source_id <> raw.household_id || '-manual-upload'
        LIMIT 10
        """
    ).fetchall()
    if invalid:
        raise LegacyAdoptionError(
            f"Onbekende ontbrekende receipt source-parent(s): {[tuple(row) for row in invalid]!r}"
        )

    inserted = 0
    for (household_id,) in connection.execute(
        "SELECT id FROM household_registry ORDER BY id"
    ).fetchall():
        source_id = f"{household_id}-manual-upload"
        if connection.execute(
            "SELECT 1 FROM receipt_sources WHERE id=? LIMIT 1", (source_id,)
        ).fetchone():
            continue
        connection.execute(
            """
            INSERT INTO receipt_sources
              (id, household_id, type, label, source_path, is_active)
            VALUES (?, ?, 'manual_upload', 'Handmatige upload', NULL, 1)
            """,
            (source_id, str(household_id)),
        )
        inserted += 1

    missing = connection.execute(
        """
        SELECT registry.id
        FROM household_registry AS registry
        LEFT JOIN receipt_sources AS source
          ON source.id=registry.id || '-manual-upload'
         AND source.household_id=registry.id
         AND source.type='manual_upload'
        WHERE source.id IS NULL LIMIT 1
        """
    ).fetchone()
    if missing:
        raise LegacyAdoptionError(
            f"Canonical manual-upload source ontbreekt voor household {missing[0]!r}"
        )
    return inserted


def _assert_runtime_invariants(connection: sqlite3.Connection) -> None:
    if not _has_table(connection, "app_users"):
        return
    invalid = connection.execute(
        """
        SELECT DISTINCT account_status FROM app_users
        WHERE account_status IS NOT NULL
          AND account_status NOT IN ('active', 'disabled', 'suspended')
        LIMIT 10
        """
    ).fetchall()
    if invalid:
        raise LegacyAdoptionError(
            f"app_users bevat niet-canonical account_status: {[row[0] for row in invalid]!r}"
        )


def _prove_preservation(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    source_tables: Sequence[str],
) -> list[dict[str, Any]]:
    proofs: list[dict[str, Any]] = []
    for table in source_tables:
        names = [item["name"] for item in _columns(source, table)]
        source_rows = _fingerprints(source, table, names)
        target_rows = _fingerprints(target, table, names)
        if source_rows - target_rows:
            raise LegacyAdoptionError(f"Productiondata niet behouden in {table!r}")
        extra = target_rows - source_rows
        if table != "receipt_sources" and extra:
            raise LegacyAdoptionError(f"Onverwachte extra rows in {table!r}")

        pk = _pk_columns(source, table)
        source_pk = _fingerprints(source, table, pk) if pk else Counter()
        target_pk = _fingerprints(target, table, pk) if pk else Counter()
        if source_pk - target_pk:
            raise LegacyAdoptionError(f"Production primary keys niet behouden in {table!r}")
        if table != "receipt_sources" and target_pk - source_pk:
            raise LegacyAdoptionError(f"Onverwachte extra primary keys in {table!r}")

        proofs.append(
            {
                "table": table,
                "source_rows": sum(source_rows.values()),
                "source_sha256": _counter_sha(source_rows),
                "primary_key": pk,
                "source_pk_sha256": _counter_sha(source_pk) if pk else None,
                "target_additional_rows": sum(extra.values()),
            }
        )
    return proofs


def adopt_legacy_production_snapshot(
    source: Path,
    working_copy: Path,
    *,
    allow_working_copy_reset: bool,
) -> dict[str, Any]:
    source = source.expanduser().resolve(strict=True)
    working_copy = working_copy.expanduser().resolve()
    if source == working_copy:
        raise LegacyAdoptionError("Immutable source and working copy must differ")
    if working_copy.exists() and not allow_working_copy_reset:
        raise LegacyAdoptionError(
            "Working copy exists; pass --allow-working-copy-reset to replace it"
        )

    source_sha = _sha256_file(source)
    with _readonly_connection(source) as src:
        _assert_integrity_only(src)
        if _has_table(src, "alembic_version"):
            raise LegacyAdoptionError("Canonical rebuild accepts only unversioned snapshots")
        source_tables = _application_tables(src)
        if not source_tables:
            raise LegacyAdoptionError("Legacy snapshot contains no application schema")
        fk_drift = classify_known_legacy_fk_drift(src)
        source_rows = sum(_count(src, table) for table in source_tables)

    canonical_schema = _build_canonical_head(working_copy)
    canonical_schema_sha = hashlib.sha256(canonical_schema.encode("utf-8")).hexdigest()

    with _readonly_connection(source) as src, sqlite3.connect(str(working_copy)) as target:
        src.row_factory = sqlite3.Row
        target.row_factory = sqlite3.Row
        canonical_only, canonical_only_counts, mapping = _preflight(
            src, target, source_tables
        )

        target.commit()
        target.execute("PRAGMA foreign_keys=OFF")
        triggers = _capture_triggers(target)
        for name, _statement in triggers:
            target.execute(f"DROP TRIGGER IF EXISTS {_q(name)}")
        target.commit()

        copied = _copy_rows(src, target, source_tables)
        manual_sources_added = _repair_receipt_boundary(target)
        for _name, statement in triggers:
            target.execute(statement)
        target.commit()
        target.execute("PRAGMA foreign_keys=ON")

        _assert_integrity_only(target)
        fk_rows = target.execute("PRAGMA foreign_key_check").fetchall()
        if fk_rows:
            raise LegacyAdoptionError(
                f"Canonical working copy has FK violations: {fk_rows[:10]!r}"
            )
        _assert_runtime_invariants(target)

        final_schema = _schema_dump(target)
        if final_schema != canonical_schema:
            raise LegacyAdoptionError(
                "Canonical schema changed during overlay: "
                f"expected={canonical_schema_sha} "
                f"actual={hashlib.sha256(final_schema.encode('utf-8')).hexdigest()}"
            )
        final_canonical_only_counts = {
            table: _count(target, table) for table in canonical_only
        }
        if final_canonical_only_counts != canonical_only_counts:
            raise LegacyAdoptionError("Migration-owned canonical-only data changed")

        proofs = _prove_preservation(src, target, source_tables)
        final_table_count = len(_application_tables(target))
        if final_table_count != EXPECTED_APPLICATION_TABLES:
            raise LegacyAdoptionError(
                f"Canonical table count changed: {final_table_count}"
            )

    if _sha256_file(source) != source_sha:
        raise LegacyAdoptionError("Immutable source changed during canonical rebuild")
    if _revision(working_copy) != HEAD_REVISION:
        raise LegacyAdoptionError(
            f"Working copy revision is {_revision(working_copy)!r}, expected {HEAD_REVISION!r}"
        )
    if sum(copied.values()) != source_rows:
        raise LegacyAdoptionError("Copied-row accounting mismatch")

    seeded = {table: count for table, count in canonical_only_counts.items() if count}
    return {
        "recovery_mode": "canonical-rebuild",
        "source_sha256": source_sha,
        "source_unversioned_tables": len(source_tables),
        "source_rows": source_rows,
        "initial_foreign_key_drift": fk_drift,
        "target_revision": HEAD_REVISION,
        "application_tables": final_table_count,
        "canonical_schema_sha256": canonical_schema_sha,
        "canonical_only_tables": canonical_only,
        "canonical_only_pre_overlay_rows": canonical_only_counts,
        "canonical_only_seeded_tables": seeded,
        "manual_sources_added": manual_sources_added,
        "source_mapping": mapping,
        "source_data_proofs": proofs,
        "working_copy_sha256": _sha256_file(working_copy),
    }


def _write_report(report: Mapping[str, Any], path: str | None) -> None:
    if path:
        output = Path(path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--working-copy", required=True, type=Path)
    parser.add_argument("--allow-working-copy-reset", action="store_true")
    parser.add_argument("--report-json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = adopt_legacy_production_snapshot(
        args.source,
        args.working_copy,
        allow_working_copy_reset=bool(args.allow_working_copy_reset),
    )
    _write_report(report, args.report_json)
    print(
        "POSTGRESQL_LEGACY_ADOPTION_SOURCE_GREEN "
        f"sha256={report['source_sha256']} "
        f"tables={report['source_unversioned_tables']} rows={report['source_rows']}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_FK_DRIFT_GREEN "
        f"violations={report['initial_foreign_key_drift']['violations']}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_CANONICAL_REBUILD_GREEN "
        f"source_tables={report['source_unversioned_tables']} "
        f"target_tables={report['application_tables']} "
        f"manual_sources_added={report['manual_sources_added']}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_SOURCE_DATA_PRESERVED_GREEN "
        f"tables={len(report['source_data_proofs'])}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_MIGRATION_OWNED_DATA_GREEN "
        f"seeded_tables={len(report['canonical_only_seeded_tables'])}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_HEAD_GREEN "
        f"revision={report['target_revision']} tables={report['application_tables']}"
    )
    print("POSTGRESQL_LEGACY_ADOPTION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
