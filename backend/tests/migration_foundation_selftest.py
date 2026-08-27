from __future__ import annotations

import gzip
import hashlib
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from capture_schema_baseline import dump_schema


BASELINE_REVISION = "20260827_01"
BASELINE_PATH = Path(__file__).resolve().parents[1] / "alembic" / "baseline_sqlite.sql.gz"
BASELINE_SQL_SHA256 = "e75cb2c16e41cd69fa42d2ffdf98dad7f3af67147ed07289edc9caa6ad4fc8b7"


def _engine_url():
    raw_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        raise RuntimeError("DATABASE_URL is required")
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _baseline_sql() -> str:
    with gzip.open(BASELINE_PATH, "rt", encoding="utf-8") as baseline_file:
        baseline = baseline_file.read()
    digest = _sha256(baseline)
    if digest != BASELINE_SQL_SHA256:
        raise AssertionError(
            f"Immutable baseline asset hash mismatch: expected={BASELINE_SQL_SHA256} actual={digest}"
        )
    return baseline


def main() -> None:
    expected_mode = str(os.getenv("REZZERV_EXPECT_MIGRATION_MODE") or "").strip()
    if expected_mode not in {"sqlite-baseline", "sqlite-stamped-runtime", "postgresql-lineage"}:
        raise RuntimeError(f"Unsupported REZZERV_EXPECT_MIGRATION_MODE: {expected_mode!r}")

    url = _engine_url()
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision != BASELINE_REVISION:
                raise AssertionError(
                    f"Expected Alembic revision {BASELINE_REVISION}, got {revision}"
                )

            dialect = connection.dialect.name
            if expected_mode.startswith("sqlite"):
                if dialect != "sqlite":
                    raise AssertionError(f"Expected SQLite, got {dialect}")
                if not url.database or url.database == ":memory:":
                    raise AssertionError("SQLite schema-contract validation requires a file database")

                baseline = _baseline_sql()
                actual = dump_schema(Path(url.database))
                if actual != baseline:
                    raise AssertionError(
                        "SQLite schema differs from immutable migration baseline: "
                        f"expected_sha256={_sha256(baseline)} actual_sha256={_sha256(actual)}"
                    )
                print(
                    "MIGRATION_SQLITE_SCHEMA_CONTRACT_GREEN "
                    f"mode={expected_mode} sha256={_sha256(actual)}"
                )
            else:
                if dialect != "postgresql":
                    raise AssertionError(f"Expected PostgreSQL, got {dialect}")
                tables = set(inspect(connection).get_table_names())
                unexpected = sorted(tables - {"alembic_version"})
                if unexpected:
                    raise AssertionError(
                        "PR2a PostgreSQL lineage must not create application tables yet: "
                        + ", ".join(unexpected)
                    )
                print("MIGRATION_POSTGRESQL_LINEAGE_GREEN")
    finally:
        engine.dispose()

    print("MIGRATION_FOUNDATION_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
