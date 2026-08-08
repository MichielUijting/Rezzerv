"""Controlled GS1 GPC import with staging, evidence and rollback backup.

The command is intentionally SQLite-only because that is the active Rezzerv
runtime. It never downloads GS1 data and requires a caller-supplied XML file
plus a source manifest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

from sqlalchemy import create_engine

from app.services.gpc_catalog_service import import_gpc_xml

TABLES = (
    "gpc_segments", "gpc_families", "gpc_classes", "gpc_bricks",
    "gpc_attribute_types", "gpc_attribute_values",
    "gpc_brick_attribute_types", "gpc_attribute_type_values", "gpc_import_runs",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_backup(source: Path, target: Path) -> None:
    """Create a transactionally consistent SQLite backup."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_conn, sqlite3.connect(target) as target_conn:
        source_conn.backup(target_conn)


def _counts(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    with sqlite3.connect(path) as conn:
        existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in TABLES:
            result[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] if table in existing else 0
    return result


def _load_manifest(path: Path, xml_path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"source_name", "source_version", "language_code", "license_reference", "xml_sha256"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"Bronmanifest mist velden: {', '.join(missing)}")
    actual_hash = _sha256(xml_path)
    if str(data["xml_sha256"]).lower() != actual_hash:
        raise ValueError("SHA-256 van XML komt niet overeen met het bronmanifest")
    return data


def run_controlled_import(xml_file: Path, manifest_file: Path, database: Path, evidence_dir: Path, apply: bool) -> dict:
    if not xml_file.is_file() or not manifest_file.is_file() or not database.is_file():
        raise FileNotFoundError("XML, bronmanifest of SQLite-database ontbreekt")
    manifest = _load_manifest(manifest_file, xml_file)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    with tempfile.TemporaryDirectory(prefix="rezzerv-gpc-") as temp_dir:
        staged_db = Path(temp_dir) / "rezzerv-staging.db"
        _sqlite_backup(database, staged_db)
        before = _counts(staged_db)
        staged_engine = create_engine(f"sqlite:///{staged_db}")
        imported = import_gpc_xml(
            xml_file,
            language_code=str(manifest["language_code"]),
            source_version=str(manifest["source_version"]),
            db_engine=staged_engine,
        )
        staged_engine.dispose()
        after = _counts(staged_db)

        report = {
            "status": "validated",
            "mode": "apply" if apply else "dry-run",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "database": str(database),
            "manifest": manifest,
            "import": imported,
            "counts_before": before,
            "counts_after": after,
            "count_delta": {key: after[key] - before[key] for key in TABLES},
            "backup": None,
        }

        if apply:
            backup = evidence_dir / f"rezzerv-pre-gpc-{timestamp}.db"
            _sqlite_backup(database, backup)
            _sqlite_backup(staged_db, database)
            report["status"] = "applied"
            report["backup"] = str(backup)
            report["database_sha256_after"] = _sha256(database)

    report_path = evidence_dir / f"gpc-import-report-{timestamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def restore_backup(backup: Path, database: Path) -> dict:
    if not backup.is_file():
        raise FileNotFoundError(f"Back-up ontbreekt: {backup}")
    _sqlite_backup(backup, database)
    return {"status": "restored", "backup": str(backup), "database": str(database), "database_sha256": _sha256(database)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Controleer en importeer een GS1 GPC XML-bestand veilig.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("import")
    validate.add_argument("xml_file")
    validate.add_argument("manifest_file")
    validate.add_argument("--database", required=True)
    validate.add_argument("--evidence-dir", required=True)
    validate.add_argument("--apply", action="store_true")
    restore = sub.add_parser("restore")
    restore.add_argument("backup")
    restore.add_argument("--database", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "restore":
            result = restore_backup(Path(args.backup), Path(args.database))
        else:
            result = run_controlled_import(
                Path(args.xml_file), Path(args.manifest_file), Path(args.database),
                Path(args.evidence_dir), bool(args.apply),
            )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
