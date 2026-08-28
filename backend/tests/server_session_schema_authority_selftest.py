from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "backend" / "alembic.ini"
PREVIOUS_REVISION = "20260827_02"
HEAD_REVISION = "20260828_01"
EXPECTED_COLUMNS = (
    "id",
    "session_token_hash",
    "user_id",
    "active_household_id",
    "issued_at",
    "expires_at",
    "session_version",
    "revoked_at",
    "replaced_by_session_id",
    "created_at",
    "updated_at",
)


def _database_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _run_alembic(path: Path, target: str, *, expect_success: bool = True) -> str:
    env = os.environ.copy()
    env["DATABASE_URL"] = _database_url(path)
    env["PYTHONPATH"] = str(REPO_ROOT / "backend")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_INI),
            "upgrade",
            target,
        ],
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
            f"Alembic upgrade {target} unexpectedly accepted malformed server_sessions"
        )
    return output


def _revision(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return str(row[0] if row else "")


def _create_legacy_server_sessions(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE server_sessions (
            id VARCHAR(64) PRIMARY KEY,
            session_token_hash VARCHAR(64) NOT NULL UNIQUE,
            user_id VARCHAR(64) NOT NULL,
            active_household_id VARCHAR(64) NOT NULL,
            issued_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            session_version INTEGER NOT NULL DEFAULT 1,
            revoked_at TIMESTAMP NULL,
            replaced_by_session_id VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_server_sessions_user_active
        ON server_sessions(user_id, revoked_at, expires_at);
        INSERT INTO server_sessions (
            id,
            session_token_hash,
            user_id,
            active_household_id,
            issued_at,
            expires_at,
            session_version,
            revoked_at,
            replaced_by_session_id,
            created_at,
            updated_at
        ) VALUES (
            'session-1',
            'hash-1',
            'user-1',
            'household-1',
            '2026-08-28 08:00:00',
            '2026-08-28 20:00:00',
            1,
            NULL,
            NULL,
            '2026-08-28 08:00:00',
            '2026-08-28 08:00:00'
        );
        """
    )
    connection.commit()


def _assert_canonical_server_sessions(
    connection: sqlite3.Connection,
    *,
    expect_seed_row: bool,
) -> None:
    columns = connection.execute('PRAGMA table_info("server_sessions")').fetchall()
    names = tuple(str(row[1]) for row in columns)
    if names != EXPECTED_COLUMNS:
        raise AssertionError(
            f"Unexpected server_sessions columns: expected={EXPECTED_COLUMNS!r} actual={names!r}"
        )
    active_household = next(row for row in columns if row[1] == "active_household_id")
    if bool(active_household[3]):
        raise AssertionError("active_household_id remained NOT NULL after authority migration")

    indexes = connection.execute('PRAGMA index_list("server_sessions")').fetchall()
    active_index = next(
        (row for row in indexes if row[1] == "idx_server_sessions_user_active"),
        None,
    )
    if active_index is None or bool(active_index[2]):
        raise AssertionError("Missing or UNIQUE idx_server_sessions_user_active")
    index_columns = tuple(
        str(row[2])
        for row in connection.execute(
            'PRAGMA index_info("idx_server_sessions_user_active")'
        ).fetchall()
    )
    if index_columns != ("user_id", "revoked_at", "expires_at"):
        raise AssertionError(f"Unexpected active index columns: {index_columns!r}")

    unique_sets = set()
    for row in indexes:
        if not bool(row[2]):
            continue
        index_name = str(row[1])
        unique_sets.add(tuple(
            str(item[2])
            for item in connection.execute(
                f'PRAGMA index_info("{index_name.replace(chr(34), chr(34) * 2)}")'
            ).fetchall()
        ))
    if ("session_token_hash",) not in unique_sets:
        raise AssertionError("session_token_hash UNIQUE contract is missing")

    rows = connection.execute(
        """
        SELECT id, session_token_hash, user_id, active_household_id,
               issued_at, expires_at, session_version, revoked_at,
               replaced_by_session_id, created_at, updated_at
        FROM server_sessions
        ORDER BY id
        """
    ).fetchall()
    if expect_seed_row:
        expected = [(
            "session-1",
            "hash-1",
            "user-1",
            "household-1",
            "2026-08-28 08:00:00",
            "2026-08-28 20:00:00",
            1,
            None,
            None,
            "2026-08-28 08:00:00",
            "2026-08-28 08:00:00",
        )]
        if rows != expected:
            raise AssertionError(f"Legacy server session data changed: {rows!r}")
    elif rows:
        raise AssertionError(f"Fresh migration unexpectedly created session rows: {rows!r}")

    if _revision(connection) != HEAD_REVISION:
        raise AssertionError(
            f"Expected revision {HEAD_REVISION}, got {_revision(connection)!r}"
        )


def _fresh_revision_02_upgrade() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Path(temp_dir) / "fresh.sqlite"
        _run_alembic(database, PREVIOUS_REVISION)
        with sqlite3.connect(database) as connection:
            existing = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='server_sessions'"
            ).fetchone()
            if existing is not None:
                raise AssertionError("Revision 02 unexpectedly contains SQLite server_sessions")
        _run_alembic(database, "head")
        with sqlite3.connect(database) as connection:
            _assert_canonical_server_sessions(connection, expect_seed_row=False)


def _legacy_runtime_table_upgrade() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Path(temp_dir) / "legacy.sqlite"
        _run_alembic(database, PREVIOUS_REVISION)
        with sqlite3.connect(database) as connection:
            _create_legacy_server_sessions(connection)
            if _revision(connection) != PREVIOUS_REVISION:
                raise AssertionError("Legacy fixture revision drifted before migration")
        _run_alembic(database, "head")
        with sqlite3.connect(database) as connection:
            _assert_canonical_server_sessions(connection, expect_seed_row=True)


def _malformed_runtime_table_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database = Path(temp_dir) / "malformed.sqlite"
        _run_alembic(database, PREVIOUS_REVISION)
        with sqlite3.connect(database) as connection:
            connection.executescript(
                """
                CREATE TABLE server_sessions (
                    id VARCHAR(64) PRIMARY KEY,
                    session_token_hash VARCHAR(64) NOT NULL UNIQUE
                );
                CREATE INDEX idx_server_sessions_user_active
                ON server_sessions(id);
                """
            )
            connection.commit()
        _run_alembic(database, "head", expect_success=False)
        with sqlite3.connect(database) as connection:
            if _revision(connection) != PREVIOUS_REVISION:
                raise AssertionError("Rejected malformed database advanced Alembic revision")
            columns = tuple(
                str(row[1])
                for row in connection.execute(
                    'PRAGMA table_info("server_sessions")'
                ).fetchall()
            )
            if columns != ("id", "session_token_hash"):
                raise AssertionError("Rejected malformed server_sessions was mutated")


def main() -> None:
    _fresh_revision_02_upgrade()
    print("SERVER_SESSION_FRESH_SQLITE_MIGRATION_GREEN")
    _legacy_runtime_table_upgrade()
    print("SERVER_SESSION_LEGACY_SQLITE_MIGRATION_GREEN")
    _malformed_runtime_table_is_rejected()
    print("SERVER_SESSION_MALFORMED_SQLITE_REJECTED_GREEN")
    print("SERVER_SESSION_SCHEMA_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
