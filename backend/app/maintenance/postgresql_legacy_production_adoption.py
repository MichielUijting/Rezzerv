"""Fail-closed adoption of unversioned legacy production SQLite snapshots.

This module is maintenance-only. It never mutates the immutable source. A
working copy is adopted only after disposable clones prove that one real
Alembic-history position upgrades to the exact canonical SQLite head schema.
Known historical receipt foreign-key drift is classified explicitly; every
other integrity or foreign-key anomaly is rejected.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from alembic.config import Config
from alembic.script import ScriptDirectory

HEAD_REVISION = "20260830_02"
BASELINE_REVISION = "20260827_01"
SYSTEM_TABLES = frozenset({"alembic_version", "sqlite_sequence"})
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = BACKEND_ROOT / "alembic.ini"
SQLITE_BASELINE = BACKEND_ROOT / "alembic" / "baseline_sqlite.sql.gz"
RECEIPT_HOUSEHOLD_TABLES = frozenset({"receipt_sources", "raw_receipts", "receipt_tables"})


class LegacyAdoptionError(RuntimeError):
    """Raised when a legacy snapshot cannot be proven safe to adopt."""


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
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [
        str(row[0])
        for row in rows
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
        ORDER BY
          CASE type
            WHEN 'table' THEN 0
            WHEN 'view' THEN 1
            WHEN 'index' THEN 2
            WHEN 'trigger' THEN 3
            ELSE 4
          END,
          name
        """
    ).fetchall()
    lines: list[str] = []
    for object_type, name, table_name, sql in rows:
        normalized = str(sql or "").strip().rstrip(";")
        if not normalized:
            continue
        lines.append(f"-- {object_type}: {name} (table={table_name})")
        lines.append(normalized + ";")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _registry_contains(connection: sqlite3.Connection, household_id: Any) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM household_registry WHERE id=? LIMIT 1",
            (str(household_id),),
        ).fetchone()
    )


def _fk_definition(
    connection: sqlite3.Connection,
    table_name: str,
    fk_id: int,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    rows = [
        row
        for row in connection.execute(
            f'PRAGMA foreign_key_list("{table_name.replace(chr(34), chr(34) * 2)}")'
        ).fetchall()
        if int(row[0]) == int(fk_id)
    ]
    if not rows:
        raise LegacyAdoptionError(
            f"foreign_key_check references unknown FK: table={table_name!r} fk_id={fk_id}"
        )
    rows.sort(key=lambda row: int(row[1]))
    parent = str(rows[0][2])
    local = tuple(str(row[3]) for row in rows)
    remote = tuple(str(row[4]) for row in rows)
    return parent, local, remote


def _row_by_rowid(
    connection: sqlite3.Connection,
    table_name: str,
    rowid: int,
) -> sqlite3.Row:
    quoted = table_name.replace('"', '""')
    row = connection.execute(
        f'SELECT rowid AS __rowid__, * FROM "{quoted}" WHERE rowid=?',
        (rowid,),
    ).fetchone()
    if row is None:
        raise LegacyAdoptionError(
            f"foreign_key_check row disappeared: table={table_name!r} rowid={rowid}"
        )
    return row


def classify_known_legacy_fk_drift(connection: sqlite3.Connection) -> dict[str, Any]:
    """Classify only the two receipt FK drift patterns found in production."""
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
        table_name = str(violation[0])
        rowid = int(violation[1])
        parent_table = str(violation[2])
        fk_id = int(violation[3])
        parent, local_columns, remote_columns = _fk_definition(
            connection, table_name, fk_id
        )
        if parent != parent_table:
            raise LegacyAdoptionError(
                f"SQLite FK metadata mismatch: check_parent={parent_table!r} metadata_parent={parent!r}"
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
                    f"Receipt household FK drift wijst niet naar household_registry: "
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
            expected_source_id = f"{household_id}-manual-upload"
            if (
                not household_id
                or source_id != expected_source_id
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
                {
                    "table": table_name,
                    "rowid": rowid,
                    "parent": parent_table,
                    "category": category,
                }
            )

    return {
        "violations": len(violations),
        "categories": dict(sorted(categories.items())),
        "samples": samples,
    }


def _backup(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    with _readonly_connection(source) as src:
        destination = sqlite3.connect(str(output))
        try:
            src.backup(destination)
            destination.commit()
        finally:
            destination.close()


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
    if len(rows) != 1:
        return ""
    return str(rows[0][0] or "").strip()


def _migration_revisions() -> list[str]:
    config = Config(str(ALEMBIC_CONFIG))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    revisions = list(script.walk_revisions(base="base", head="head"))
    ordered = [str(item.revision) for item in reversed(revisions)]
    if not ordered or ordered[-1] != HEAD_REVISION:
        raise LegacyAdoptionError(
            f"Unexpected Alembic head while building legacy adoption candidates: {ordered[-1:]!r}"
        )
    if BASELINE_REVISION not in ordered:
        raise LegacyAdoptionError("Immutable SQLite baseline revision ontbreekt in Alembic history")
    return ordered


def _upgrade_from_candidate(path: Path, candidate_revision: str) -> tuple[bool, str]:
    stamp = _run_alembic(path, "stamp", candidate_revision)
    if stamp.returncode != 0:
        return False, (stamp.stderr or stamp.stdout)[-2000:]
    upgrade = _run_alembic(path, "upgrade", "head")
    if upgrade.returncode != 0:
        return False, (upgrade.stderr or upgrade.stdout)[-2000:]
    if _revision(path) != HEAD_REVISION:
        return False, f"upgrade ended at {_revision(path)!r}"
    connection = sqlite3.connect(str(path))
    try:
        _assert_integrity_only(connection)
        fk_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        if fk_rows:
            return False, f"foreign_key_check after upgrade: {fk_rows[:10]!r}"
    finally:
        connection.close()
    return True, ""


def _build_canonical_head(path: Path) -> str:
    path.unlink(missing_ok=True)
    with gzip.open(SQLITE_BASELINE, "rt", encoding="utf-8") as handle:
        baseline_sql = handle.read()
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(baseline_sql)
        connection.commit()
    finally:
        connection.close()
    ok, detail = _upgrade_from_candidate(path, BASELINE_REVISION)
    if not ok:
        raise LegacyAdoptionError(
            "Canonical SQLite head kon niet uit immutable baseline worden opgebouwd: " + detail
        )
    connection = sqlite3.connect(str(path))
    try:
        return _schema_dump(connection)
    finally:
        connection.close()


def _candidate_matches_canonical(source: Path, candidate: str, canonical_schema: str, probe: Path) -> tuple[bool, str]:
    _backup(source, probe)
    ok, detail = _upgrade_from_candidate(probe, candidate)
    if not ok:
        return False, detail
    connection = sqlite3.connect(str(probe))
    try:
        actual = _schema_dump(connection)
    finally:
        connection.close()
    if actual != canonical_schema:
        return False, (
            "final schema differs from canonical head: "
            f"expected_sha256={hashlib.sha256(canonical_schema.encode()).hexdigest()} "
            f"actual_sha256={hashlib.sha256(actual.encode()).hexdigest()}"
        )
    return True, ""


def adopt_legacy_production_snapshot(
    source: Path,
    working_copy: Path,
    *,
    allow_working_copy_reset: bool,
) -> dict[str, Any]:
    source = source.expanduser().resolve(strict=True)
    working_copy = working_copy.expanduser().resolve()
    if source == working_copy:
        raise LegacyAdoptionError("Immutable source and working copy must be different files")
    if working_copy.exists() and not allow_working_copy_reset:
        raise LegacyAdoptionError(
            "Working copy exists; pass --allow-working-copy-reset to replace it explicitly"
        )

    source_sha_before = _sha256_file(source)
    with _readonly_connection(source) as connection:
        _assert_integrity_only(connection)
        if _has_table(connection, "alembic_version"):
            raise LegacyAdoptionError(
                "Legacy production adoption is only for unversioned SQLite snapshots"
            )
        if not _application_tables(connection):
            raise LegacyAdoptionError("Legacy SQLite snapshot contains no application schema")
        fk_drift = classify_known_legacy_fk_drift(connection)
        legacy_table_count = len(_application_tables(connection))

    working_copy.parent.mkdir(parents=True, exist_ok=True)
    _backup(source, working_copy)

    with tempfile.TemporaryDirectory(prefix="rezzerv-legacy-adoption-") as temporary:
        temporary_root = Path(temporary)
        canonical_path = temporary_root / "canonical.sqlite"
        probe_path = temporary_root / "probe.sqlite"
        canonical_schema = _build_canonical_head(canonical_path)
        canonical_schema_sha = hashlib.sha256(canonical_schema.encode("utf-8")).hexdigest()

        recognized: list[str] = []
        rejected: dict[str, str] = {}
        revisions = _migration_revisions()
        for candidate in revisions[:-1]:
            matches, detail = _candidate_matches_canonical(
                source, candidate, canonical_schema, probe_path
            )
            if matches:
                recognized.append(candidate)
            else:
                rejected[candidate] = detail[-500:]

        if not recognized:
            raise LegacyAdoptionError(
                "Unversioned production schema matches no safe Alembic adoption point; "
                f"tried={revisions[:-1]!r} rejected={rejected!r}"
            )
        selected_revision = recognized[-1]

        ok, detail = _upgrade_from_candidate(working_copy, selected_revision)
        if not ok:
            raise LegacyAdoptionError(
                f"Working-copy upgrade from proven revision {selected_revision} failed: {detail}"
            )
        with sqlite3.connect(str(working_copy)) as connection:
            _assert_integrity_only(connection)
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_keys:
                raise LegacyAdoptionError(
                    f"Working copy has FK violations after adoption: {foreign_keys[:10]!r}"
                )
            final_schema = _schema_dump(connection)
            final_table_count = len(_application_tables(connection))
        if final_schema != canonical_schema:
            raise LegacyAdoptionError("Working-copy final schema differs from proven canonical head")

    source_sha_after = _sha256_file(source)
    if source_sha_after != source_sha_before:
        raise LegacyAdoptionError(
            "Immutable legacy source changed during adoption attempt: "
            f"before={source_sha_before} after={source_sha_after}"
        )

    report = {
        "source_sha256": source_sha_before,
        "source_unversioned_tables": legacy_table_count,
        "initial_foreign_key_drift": fk_drift,
        "recognized_adoption_revisions": recognized,
        "selected_adoption_revision": selected_revision,
        "target_revision": HEAD_REVISION,
        "canonical_schema_sha256": canonical_schema_sha,
        "application_tables": final_table_count,
        "working_copy_sha256": _sha256_file(working_copy),
    }
    return report


def _write_report(report: Mapping[str, Any], path: str | None) -> None:
    if not path:
        return
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
        f"sha256={report['source_sha256']} tables={report['source_unversioned_tables']}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_FK_DRIFT_GREEN "
        f"violations={report['initial_foreign_key_drift']['violations']}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_HISTORY_GREEN "
        f"selected={report['selected_adoption_revision']} "
        f"recognized={len(report['recognized_adoption_revisions'])}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_HEAD_GREEN "
        f"revision={report['target_revision']} tables={report['application_tables']}"
    )
    print("POSTGRESQL_LEGACY_ADOPTION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
