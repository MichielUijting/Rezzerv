from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "backend" / "alembic.ini"
PREVIOUS_REVISION = "20260828_01"
HEAD_REVISION = "20260829_09"
RECEIPT_TABLES = ("raw_receipts", "receipt_tables", "receipt_table_lines")


def _database_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _run_alembic(path: Path, target: str, *, expect_success: bool = True) -> str:
    env = os.environ.copy()
    env["DATABASE_URL"] = _database_url(path)
    env["PYTHONPATH"] = str(REPO_ROOT / "backend")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", target],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    output = result.stdout + result.stderr
    if expect_success and result.returncode != 0:
        raise AssertionError(f"Alembic upgrade {target} failed:\n{output}")
    if not expect_success and result.returncode == 0:
        raise AssertionError(
            f"Alembic upgrade {target} unexpectedly accepted receipt lifecycle drift"
        )
    return output


def _revision(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return str(row[0] if row else "")


def _receipt_schema_snapshot(connection: sqlite3.Connection) -> tuple[tuple[str, str, str, str], ...]:
    placeholders = ",".join("?" for _ in RECEIPT_TABLES)
    return tuple(
        (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
        for row in connection.execute(
            f"SELECT type, name, tbl_name, sql FROM sqlite_master "
            f"WHERE tbl_name IN ({placeholders}) AND sql IS NOT NULL "
            f"ORDER BY type, name",
            RECEIPT_TABLES,
        ).fetchall()
    )


def _canonical_schema_is_validation_only() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Path(temp_dir) / "canonical.sqlite"
        _run_alembic(database, PREVIOUS_REVISION)
        with sqlite3.connect(database) as connection:
            before = _receipt_schema_snapshot(connection)
            if _revision(connection) != PREVIOUS_REVISION:
                raise AssertionError("Canonical fixture revision drifted before validation")
        _run_alembic(database, "head")
        with sqlite3.connect(database) as connection:
            after = _receipt_schema_snapshot(connection)
            if before != after:
                raise AssertionError("Receipt authority revision mutated canonical SQLite schema")
            if _revision(connection) != HEAD_REVISION:
                raise AssertionError(
                    f"Expected revision {HEAD_REVISION}, got {_revision(connection)!r}"
                )


def _missing_index_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Path(temp_dir) / "missing-index.sqlite"
        _run_alembic(database, PREVIOUS_REVISION)
        with sqlite3.connect(database) as connection:
            connection.execute("DROP INDEX idx_receipt_tables_workflow_state")
            connection.commit()
        _run_alembic(database, "head", expect_success=False)
        with sqlite3.connect(database) as connection:
            if _revision(connection) != PREVIOUS_REVISION:
                raise AssertionError("Rejected receipt index drift advanced Alembic revision")
            index = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_receipt_tables_workflow_state'"
            ).fetchone()
            if index is not None:
                raise AssertionError("Rejected receipt index drift was mutated")


def _missing_trigger_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Path(temp_dir) / "missing-trigger.sqlite"
        _run_alembic(database, PREVIOUS_REVISION)
        with sqlite3.connect(database) as connection:
            connection.execute("DROP TRIGGER trg_receipt_tables_preserve_explicit_approval")
            connection.commit()
        _run_alembic(database, "head", expect_success=False)
        with sqlite3.connect(database) as connection:
            if _revision(connection) != PREVIOUS_REVISION:
                raise AssertionError("Rejected receipt trigger drift advanced Alembic revision")
            trigger = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='trg_receipt_tables_preserve_explicit_approval'"
            ).fetchone()
            if trigger is not None:
                raise AssertionError("Rejected receipt trigger drift was mutated")


def main() -> None:
    _canonical_schema_is_validation_only()
    print("RECEIPT_LIFECYCLE_CANONICAL_SQLITE_VALIDATION_GREEN")
    _missing_index_is_rejected()
    print("RECEIPT_LIFECYCLE_MALFORMED_INDEX_REJECTED_GREEN")
    _missing_trigger_is_rejected()
    print("RECEIPT_LIFECYCLE_MALFORMED_TRIGGER_REJECTED_GREEN")
    print("RECEIPT_LIFECYCLE_SCHEMA_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
