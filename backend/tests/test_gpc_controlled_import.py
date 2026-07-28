from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from app.cli.import_gpc_catalog_controlled import restore_backup, run_controlled_import

XML = """<?xml version='1.0' encoding='UTF-8'?>
<schema><segment code='50000000' text='Voeding'><family code='50100000' text='Groenten'><class code='50101700' text='Onbewerkt'><brick code='10006144' text='Mosterdblad'/></class></family></segment></schema>
"""


def _database(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        conn.execute("INSERT INTO sentinel VALUES ('original')")


def _source(tmp_path: Path) -> tuple[Path, Path]:
    xml = tmp_path / "nl.xml"
    xml.write_text(XML, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "source_name": "GS1 GPC NL test",
        "source_version": "ci",
        "language_code": "nl",
        "license_reference": "test-only",
        "xml_sha256": hashlib.sha256(xml.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    return xml, manifest


def test_dry_run_does_not_change_runtime_database(tmp_path: Path) -> None:
    database = tmp_path / "rezzerv.db"
    _database(database)
    xml, manifest = _source(tmp_path)
    before = database.read_bytes()
    result = run_controlled_import(xml, manifest, database, tmp_path / "evidence", False)
    assert result["status"] == "validated"
    assert result["counts_after"]["gpc_bricks"] == 1
    assert database.read_bytes() == before


def test_apply_creates_backup_and_restore_recovers_database(tmp_path: Path) -> None:
    database = tmp_path / "rezzerv.db"
    _database(database)
    xml, manifest = _source(tmp_path)
    result = run_controlled_import(xml, manifest, database, tmp_path / "evidence", True)
    assert result["status"] == "applied"
    backup = Path(result["backup"])
    assert backup.is_file()
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT description FROM gpc_bricks WHERE brick_code='10006144'").fetchone() == ("Mosterdblad",)
    restore_backup(backup, database)
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT value FROM sentinel").fetchone() == ("original",)
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gpc_bricks'").fetchone() is None
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_manifest_hash_mismatch_blocks_import(tmp_path: Path) -> None:
    database = tmp_path / "rezzerv.db"
    _database(database)
    xml, manifest = _source(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["xml_sha256"] = "0" * 64
    manifest.write_text(json.dumps(data), encoding="utf-8")
    try:
        run_controlled_import(xml, manifest, database, tmp_path / "evidence", False)
    except ValueError as exc:
        assert "SHA-256" in str(exc)
    else:
        raise AssertionError("Hash mismatch moet import blokkeren")
