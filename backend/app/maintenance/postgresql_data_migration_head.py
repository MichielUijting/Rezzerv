"""Locked-head entrypoint for PostgreSQL production-data migration."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Sequence

from app.maintenance import postgresql_data_migration as migration

HEAD_REVISION = "20260902_01"
EXPECTED_APPLICATION_TABLES = 88


def _assert_snapshot_storage_integrity(connection: sqlite3.Connection) -> None:
    """Require physical SQLite integrity while leaving FK policy to adoption/import."""
    result = [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]
    if result != ["ok"]:
        raise migration.MigrationError(f"SQLite integrity_check failed: {result!r}")


def _create_consistent_snapshot_for_locked_head(source: Path, output: Path) -> str:
    """Capture legacy production safely before classifying known FK drift.

    A production snapshot is an immutable capture boundary, not an approval of
    its relational state. Physical SQLite corruption is rejected here. Known
    legacy foreign-key drift is classified fail-closed by the subsequent
    legacy-adoption runner; the normal importer still requires a fully clean
    foreign_key_check before any PostgreSQL data copy.
    """
    source = source.expanduser().resolve(strict=True)
    output = output.expanduser().resolve()
    if source == output:
        raise migration.MigrationError("Snapshot output must differ from the source database")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)

    with migration._sqlite_readonly_connection(source) as src:
        _assert_snapshot_storage_integrity(src)
        destination = sqlite3.connect(str(output))
        try:
            src.backup(destination)
            destination.commit()
            _assert_snapshot_storage_integrity(destination)
        finally:
            destination.close()

    return hashlib.sha256(output.read_bytes()).hexdigest()


def _configure_locked_head() -> None:
    migration.HEAD_REVISION = HEAD_REVISION
    migration.EXPECTED_APPLICATION_TABLES = EXPECTED_APPLICATION_TABLES
    migration.create_consistent_snapshot = _create_consistent_snapshot_for_locked_head


def main(argv: Sequence[str] | None = None) -> int:
    _configure_locked_head()
    return migration.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
