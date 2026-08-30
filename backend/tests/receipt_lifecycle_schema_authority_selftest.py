from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "backend" / "alembic.ini"
LIFECYCLE_PREVIOUS_REVISION = "20260828_01"
HOUSEHOLD_AUTHORITY_PREVIOUS_REVISION = "20260830_01"
HEAD_REVISION = "20260830_02"
RECEIPT_HOUSEHOLD_TABLES = ("receipt_sources", "raw_receipts", "receipt_tables")
MANUAL_SOURCE_TRIGGER = "trg_raw_receipts_ensure_manual_source"


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


def _table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> tuple[tuple[str, str, int, object, int], ...]:
    quoted = '"' + table_name.replace('"', '""') + '"'
    return tuple(
        (
            str(row[1]),
            str(row[2] or "").upper(),
            int(row[3] or 0),
            row[4],
            int(row[5] or 0),
        )
        for row in connection.execute(f"PRAGMA table_info({quoted})").fetchall()
    )


def _index_contract(
    connection: sqlite3.Connection,
    table_name: str,
) -> tuple[tuple[str, int, str, int, tuple[str, ...]], ...]:
    quoted = '"' + table_name.replace('"', '""') + '"'
    indexes: list[tuple[str, int, str, int, tuple[str, ...]]] = []
    for row in connection.execute(f"PRAGMA index_list({quoted})").fetchall():
        name = str(row[1])
        if name.startswith("sqlite_autoindex_"):
            continue
        index_quoted = '"' + name.replace('"', '""') + '"'
        columns = tuple(
            str(info[2])
            for info in connection.execute(f"PRAGMA index_info({index_quoted})").fetchall()
        )
        indexes.append((name, int(row[2] or 0), str(row[3] or ""), int(row[4] or 0), columns))
    return tuple(sorted(indexes))


def _trigger_contract(
    connection: sqlite3.Connection,
    table_name: str,
    *,
    exclude: set[str] | None = None,
) -> tuple[tuple[str, str], ...]:
    excluded = exclude or set()
    rows = connection.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type='trigger' AND tbl_name=? AND sql IS NOT NULL
        ORDER BY name
        """,
        (table_name,),
    ).fetchall()
    return tuple(
        (str(name), str(sql).strip())
        for name, sql in rows
        if str(name) not in excluded
    )


def _foreign_key_contract(
    connection: sqlite3.Connection,
    table_name: str,
) -> tuple[tuple[str, str, str, str, str], ...]:
    quoted = '"' + table_name.replace('"', '""') + '"'
    rows = connection.execute(f"PRAGMA foreign_key_list({quoted})").fetchall()
    return tuple(
        sorted(
            (
                str(row[3]),
                str(row[2]),
                str(row[4]),
                str(row[5]),
                str(row[6]),
            )
            for row in rows
        )
    )


def _household_fk_parent(
    connection: sqlite3.Connection,
    table_name: str,
) -> tuple[str, str]:
    matches = [
        item
        for item in _foreign_key_contract(connection, table_name)
        if item[0] == "household_id"
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"{table_name}.household_id requires exactly one FK; actual={matches!r}"
        )
    return matches[0][1], matches[0][2]


def _non_household_fk_contract(
    connection: sqlite3.Connection,
    table_name: str,
) -> tuple[tuple[str, str, str, str, str], ...]:
    return tuple(
        item
        for item in _foreign_key_contract(connection, table_name)
        if item[0] != "household_id"
    )


def _household_authority_delta_is_exact() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Path(temp_dir) / "receipt-household-authority.sqlite"
        _run_alembic(database, HOUSEHOLD_AUTHORITY_PREVIOUS_REVISION)
        with sqlite3.connect(database) as connection:
            if _revision(connection) != HOUSEHOLD_AUTHORITY_PREVIOUS_REVISION:
                raise AssertionError("Receipt household-authority fixture did not reach _01")
            before_columns = {
                table: _table_columns(connection, table)
                for table in RECEIPT_HOUSEHOLD_TABLES
            }
            before_indexes = {
                table: _index_contract(connection, table)
                for table in RECEIPT_HOUSEHOLD_TABLES
            }
            before_triggers = {
                table: _trigger_contract(connection, table)
                for table in RECEIPT_HOUSEHOLD_TABLES
            }
            before_other_fks = {
                table: _non_household_fk_contract(connection, table)
                for table in RECEIPT_HOUSEHOLD_TABLES
            }
            for table in RECEIPT_HOUSEHOLD_TABLES:
                if _household_fk_parent(connection, table) != ("households", "id"):
                    raise AssertionError(
                        f"Expected legacy households.id parent before _02 for {table}"
                    )
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
                (MANUAL_SOURCE_TRIGGER,),
            ).fetchone() is not None:
                raise AssertionError("Manual-source trigger already existed before _02")

        _run_alembic(database, "head")
        with sqlite3.connect(database) as connection:
            if _revision(connection) != HEAD_REVISION:
                raise AssertionError(
                    f"Expected revision {HEAD_REVISION}, got {_revision(connection)!r}"
                )
            for table in RECEIPT_HOUSEHOLD_TABLES:
                after_columns = _table_columns(connection, table)
                if after_columns != before_columns[table]:
                    raise AssertionError(
                        f"{table} column contract drifted outside household authority: "
                        f"before={before_columns[table]!r} after={after_columns!r}"
                    )
                after_indexes = _index_contract(connection, table)
                if after_indexes != before_indexes[table]:
                    raise AssertionError(
                        f"{table} index contract drifted: "
                        f"before={before_indexes[table]!r} after={after_indexes!r}"
                    )
                after_other_fks = _non_household_fk_contract(connection, table)
                if after_other_fks != before_other_fks[table]:
                    raise AssertionError(
                        f"{table} non-household FK contract drifted: "
                        f"before={before_other_fks[table]!r} after={after_other_fks!r}"
                    )
                if _household_fk_parent(connection, table) != ("household_registry", "id"):
                    raise AssertionError(
                        f"{table}.household_id did not cut over to household_registry.id"
                    )

                after_existing_triggers = _trigger_contract(
                    connection,
                    table,
                    exclude={MANUAL_SOURCE_TRIGGER},
                )
                if after_existing_triggers != before_triggers[table]:
                    raise AssertionError(
                        f"{table} existing trigger contract drifted: "
                        f"before={before_triggers[table]!r} after={after_existing_triggers!r}"
                    )

            manual_trigger = connection.execute(
                "SELECT tbl_name, sql FROM sqlite_master "
                "WHERE type='trigger' AND name=?",
                (MANUAL_SOURCE_TRIGGER,),
            ).fetchone()
            if manual_trigger is None or str(manual_trigger[0]) != "raw_receipts":
                raise AssertionError("Manual-source trigger is not owned by raw_receipts")
            normalized_trigger = " ".join(str(manual_trigger[1] or "").lower().split())
            for fragment in (
                "before insert on raw_receipts",
                "new.source_id = new.household_id || '-manual-upload'",
                "insert or ignore into receipt_sources",
            ):
                if fragment not in normalized_trigger:
                    raise AssertionError(
                        f"Manual-source trigger misses {fragment!r}: {manual_trigger[1]!r}"
                    )

            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise AssertionError(
                    f"Receipt household authority head has FK violations: {violations[:10]!r}"
                )


def _missing_index_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Path(temp_dir) / "missing-index.sqlite"
        _run_alembic(database, LIFECYCLE_PREVIOUS_REVISION)
        with sqlite3.connect(database) as connection:
            connection.execute("DROP INDEX idx_receipt_tables_workflow_state")
            connection.commit()
        _run_alembic(database, "head", expect_success=False)
        with sqlite3.connect(database) as connection:
            if _revision(connection) != LIFECYCLE_PREVIOUS_REVISION:
                raise AssertionError("Rejected receipt index drift advanced Alembic revision")
            index = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_receipt_tables_workflow_state'"
            ).fetchone()
            if index is not None:
                raise AssertionError("Rejected receipt index drift was mutated")


def _missing_trigger_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Path(temp_dir) / "missing-trigger.sqlite"
        _run_alembic(database, LIFECYCLE_PREVIOUS_REVISION)
        with sqlite3.connect(database) as connection:
            connection.execute("DROP TRIGGER trg_receipt_tables_preserve_explicit_approval")
            connection.commit()
        _run_alembic(database, "head", expect_success=False)
        with sqlite3.connect(database) as connection:
            if _revision(connection) != LIFECYCLE_PREVIOUS_REVISION:
                raise AssertionError("Rejected receipt trigger drift advanced Alembic revision")
            trigger = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='trg_receipt_tables_preserve_explicit_approval'"
            ).fetchone()
            if trigger is not None:
                raise AssertionError("Rejected receipt trigger drift was mutated")


def main() -> None:
    _household_authority_delta_is_exact()
    print("RECEIPT_HOUSEHOLD_AUTHORITY_SQLITE_DELTA_GREEN")
    print("RECEIPT_LIFECYCLE_CANONICAL_SQLITE_VALIDATION_GREEN")
    _missing_index_is_rejected()
    print("RECEIPT_LIFECYCLE_MALFORMED_INDEX_REJECTED_GREEN")
    _missing_trigger_is_rejected()
    print("RECEIPT_LIFECYCLE_MALFORMED_TRIGGER_REJECTED_GREEN")
    print("RECEIPT_LIFECYCLE_SCHEMA_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
