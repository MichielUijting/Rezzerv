"""Database foundation smoke test for SQLite compatibility and real PostgreSQL."""

from __future__ import annotations

import os

from sqlalchemy import text

from app.db import DATASTORE_KIND, SessionLocal, engine, get_runtime_datastore_info


_TABLE = "rezzerv_database_foundation_smoke"


def _assert_runtime_diagnostics() -> None:
    expected = str(os.getenv("REZZERV_EXPECT_DATASTORE") or DATASTORE_KIND).strip()
    assert DATASTORE_KIND == expected, (DATASTORE_KIND, expected)

    info = get_runtime_datastore_info()
    assert info["datastore"] == expected
    assert info.get("database_url")

    secret = str(os.getenv("REZZERV_DATABASE_TEST_SECRET") or "").strip()
    if secret:
        assert secret not in str(info)

    if expected == "postgresql":
        assert engine.dialect.driver == "psycopg", engine.dialect.driver
        assert info.get("database")
        assert info.get("host")


def _assert_session_and_transactions() -> None:
    with SessionLocal() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1

    with engine.connect() as connection:
        try:
            connection.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
            connection.commit()
            connection.execute(
                text(
                    f"CREATE TABLE {_TABLE} ("
                    "id INTEGER PRIMARY KEY, value VARCHAR(64) NOT NULL)"
                )
            )
            connection.commit()

            connection.execute(
                text(f"INSERT INTO {_TABLE} (id, value) VALUES (1, 'rollback')")
            )
            connection.rollback()
            assert connection.execute(text(f"SELECT COUNT(*) FROM {_TABLE}")).scalar_one() == 0

            connection.execute(
                text(f"INSERT INTO {_TABLE} (id, value) VALUES (1, 'commit')")
            )
            connection.commit()
            assert connection.execute(text(f"SELECT COUNT(*) FROM {_TABLE}")).scalar_one() == 1
        finally:
            connection.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
            connection.commit()

    engine.dispose()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def main() -> None:
    _assert_runtime_diagnostics()
    _assert_session_and_transactions()
    print("DATABASE_FOUNDATION_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
