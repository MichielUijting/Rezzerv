"""Run a full controlled English GPC + Dutch overlay rehearsal on isolated SQLite."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET

from sqlalchemy import create_engine

from app.cli.import_gpc_catalog_controlled import restore_backup, run_controlled_import
from app.services.gpc_official_translation_source import download_official_gpc_translation_sync
from app.services.gpc_translation_service import import_gpc_translations_csv, translation_coverage

ENTITY_TAGS = {
    "segment": "segment",
    "family": "family",
    "class": "class",
    "brick": "brick",
    "attribute_type": "attType",
    "attribute_value": "attValue",
}
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
HEAD_REVISION = "20260829_11"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _extract(xml_path: Path) -> dict[str, dict[str, str]]:
    reverse = {tag: entity for entity, tag in ENTITY_TAGS.items()}
    result = {entity: {} for entity in ENTITY_TAGS}
    for element in ET.parse(xml_path).getroot().iter():
        entity = reverse.get(_local_name(element.tag))
        if not entity:
            continue
        code = (element.get("code") or "").strip()
        label = (element.get("text") or "").strip()
        if code and label:
            result[entity][code] = label
    return result


def _schema_snapshot(path: Path) -> list[tuple[str, str, str]]:
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT type, name, COALESCE(sql, '') FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()


def _migrate_rehearsal_database(database: Path) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    env["PYTHONPATH"] = str(BACKEND_ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Alembic GPC rehearsal migration failed:\n" + result.stdout + result.stderr
        )
    with sqlite3.connect(database) as conn:
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    if revision != (HEAD_REVISION,):
        raise RuntimeError(
            f"GPC rehearsal verwacht Alembic {HEAD_REVISION}, kreeg {revision!r}"
        )


def _write_manifest(download: dict, path: Path) -> None:
    path.write_text(json.dumps({
        "source_name": "GS1 GPC Browser",
        "source_version": download["publication_version"],
        "language_code": download["language_code"],
        "license_reference": "GS1 GPC Browser publication; use subject to GS1 terms",
        "xml_sha256": download["file_sha256"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_translation_csv(english_xml: Path, dutch_xml: Path, path: Path) -> int:
    english = _extract(english_xml)
    dutch = _extract(dutch_xml)
    rows = []
    for entity_type in ENTITY_TAGS:
        missing = sorted(set(english[entity_type]) - set(dutch[entity_type]))
        if missing:
            raise ValueError(f"Nederlandse publicatie mist {len(missing)} codes voor {entity_type}")
        for code, source_text in sorted(english[entity_type].items()):
            rows.append({
                "entity_type": entity_type,
                "entity_code": code,
                "source_text": source_text,
                "language_code": "nl",
                "translated_text": dutch[entity_type][code],
                "translation_source": "Official GS1 GPC Browser nl",
                "reviewed": "1",
            })
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "entity_type", "entity_code", "source_text", "language_code",
            "translated_text", "translation_source", "reviewed",
        ))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = output_dir / "sources"
    evidence = output_dir / "evidence"
    sources.mkdir(exist_ok=True)
    evidence.mkdir(exist_ok=True)

    english = download_official_gpc_translation_sync(sources / "en", language_code="en", file_format="xml")
    dutch = download_official_gpc_translation_sync(sources / "nl", language_code="nl", file_format="xml")
    if english["publication_version"] != dutch["publication_version"]:
        raise ValueError("Engelse en Nederlandse publicatieversie verschillen")

    database = output_dir / "rezzerv-import-rehearsal.db"
    database.unlink(missing_ok=True)
    _migrate_rehearsal_database(database)
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE rehearsal_baseline (id INTEGER PRIMARY KEY, marker TEXT NOT NULL)")
        conn.execute("INSERT INTO rehearsal_baseline(marker) VALUES ('before-gpc')")
    initial_schema = _schema_snapshot(database)
    manifest = sources / "english-source-manifest.json"
    _write_manifest(english, manifest)

    dry_run = run_controlled_import(Path(english["file_path"]), manifest, database, evidence, False)
    applied = run_controlled_import(Path(english["file_path"]), manifest, database, evidence, True)
    backup = Path(applied["backup"])

    translations_csv = sources / "gpc-nl-translations.csv"
    translation_rows = _write_translation_csv(Path(english["file_path"]), Path(dutch["file_path"]), translations_csv)
    engine = create_engine(f"sqlite:///{database}")
    try:
        first_translation_import = import_gpc_translations_csv(translations_csv, db_engine=engine)
        second_translation_import = import_gpc_translations_csv(translations_csv, db_engine=engine)
        coverage = translation_coverage(db_engine=engine)
    finally:
        engine.dispose()

    with sqlite3.connect(database) as conn:
        integrity_after_import = conn.execute("PRAGMA integrity_check").fetchone()[0]
    restored = restore_backup(backup, database)
    with sqlite3.connect(database) as conn:
        integrity_after_restore = conn.execute("PRAGMA integrity_check").fetchone()[0]
        baseline_marker = conn.execute("SELECT marker FROM rehearsal_baseline WHERE id=1").fetchone()[0]
    restored_schema = _schema_snapshot(database)

    report = {
        "status": "success",
        "alembic_revision": HEAD_REVISION,
        "publication_version": english["publication_version"],
        "english_sha256": english["file_sha256"],
        "dutch_sha256": dutch["file_sha256"],
        "translation_rows": translation_rows,
        "dry_run": dry_run,
        "apply": applied,
        "first_translation_import": first_translation_import,
        "second_translation_import": second_translation_import,
        "coverage": coverage,
        "integrity_after_import": integrity_after_import,
        "restore": restored,
        "integrity_after_restore": integrity_after_restore,
        "initial_schema": initial_schema,
        "restored_schema": restored_schema,
        "baseline_marker_after_restore": baseline_marker,
        "restored_database_sha256": _sha256(database),
    }
    if not coverage["complete"] or integrity_after_import != "ok" or integrity_after_restore != "ok":
        raise RuntimeError("Import-, dekkings- of integriteitscontrole faalde")
    if initial_schema != restored_schema or baseline_marker != "before-gpc":
        raise RuntimeError("Rollback herstelde de oorspronkelijke logische databasestatus niet")
    report_path = evidence / "gpc-bilingual-import-rehearsal-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main(argv: list[str] | None = None) -> int:
    if not argv or len(argv) != 1:
        print("Gebruik: python -m app.cli.rehearse_gpc_bilingual_import <output-dir>", file=sys.stderr)
        return 2
    try:
        result = run(Path(argv[0]))
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "failed", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
