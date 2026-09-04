"""Shared PostgreSQL boundary for Rezzerv acceptance and integration tests.

This module centralizes the production-like database contract used by canonical
acceptance authorities. It never creates schema objects. Schema ownership and
migrations remain migrator responsibilities; application scenarios use the
DML-only runtime role.

The boundary fails closed when:
- DATABASE_URL or MIGRATION_DATABASE_URL is missing;
- either URL is not PostgreSQL;
- runtime and migrator point at different databases;
- runtime and migrator resolve to the same database user;
- the runtime role has schema CREATE authority;
- the migrator lacks schema CREATE authority;
- the database Alembic head differs from the repository head.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _required_database_url(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} ontbreekt voor PostgreSQL acceptance test")
    if value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


def _postgresql_engine(name: str) -> Engine:
    engine = create_engine(_required_database_url(name), future=True)
    if engine.dialect.name != "postgresql":
        dialect = engine.dialect.name
        engine.dispose()
        raise RuntimeError(
            f"{name} moet PostgreSQL zijn voor acceptance tests; ontvangen dialect={dialect}"
        )
    return engine


def create_postgresql_runtime_test_engine() -> Engine:
    """Return a PostgreSQL runtime engine and prove it is DML-only."""

    engine = _postgresql_engine("DATABASE_URL")
    try:
        with engine.connect() as conn:
            can_create = bool(
                conn.execute(
                    text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                ).scalar_one()
            )
            if can_create:
                raise RuntimeError("PostgreSQL test runtime-role heeft onverwacht schema CREATE")
        return engine
    except Exception:
        engine.dispose()
        raise


def create_postgresql_migration_test_engine() -> Engine:
    """Return the PostgreSQL migrator engine and prove it owns schema CREATE."""

    engine = _postgresql_engine("MIGRATION_DATABASE_URL")
    try:
        with engine.connect() as conn:
            can_create = bool(
                conn.execute(
                    text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                ).scalar_one()
            )
            if not can_create:
                raise RuntimeError("PostgreSQL test migrator mist schema CREATE authority")
        return engine
    except Exception:
        engine.dispose()
        raise


def expected_alembic_head() -> str:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Canonical Alembic verwacht exact één head, ontvangen={heads}")
    return str(heads[0])


def postgresql_acceptance_snapshot(*, require_alembic_head: bool = True) -> dict[str, Any]:
    """Prove the shared runtime/migrator boundary and optionally the Alembic head."""

    policy = str(os.getenv("REZZERV_DATASTORE_POLICY") or "").strip().lower()
    if policy and policy != "postgresql-only":
        raise RuntimeError(
            "Acceptance foundation vereist REZZERV_DATASTORE_POLICY=postgresql-only; "
            f"ontvangen={policy!r}"
        )

    runtime_engine = create_postgresql_runtime_test_engine()
    migration_engine = create_postgresql_migration_test_engine()
    try:
        with runtime_engine.connect() as conn:
            runtime_user = str(conn.execute(text("SELECT current_user")).scalar_one())
            runtime_database = str(conn.execute(text("SELECT current_database()" )).scalar_one())
            runtime_create = bool(
                conn.execute(
                    text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                ).scalar_one()
            )

        with migration_engine.connect() as conn:
            migrator_user = str(conn.execute(text("SELECT current_user")).scalar_one())
            migrator_database = str(conn.execute(text("SELECT current_database()" )).scalar_one())
            migrator_create = bool(
                conn.execute(
                    text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                ).scalar_one()
            )
            database_heads: list[str] = []
            repository_head: str | None = None
            if require_alembic_head:
                repository_head = expected_alembic_head()
                if not inspect(conn).has_table("alembic_version"):
                    raise RuntimeError("Acceptance database mist alembic_version")
                database_heads = [
                    str(row[0])
                    for row in conn.execute(
                        text("SELECT version_num FROM alembic_version ORDER BY version_num")
                    )
                ]
                if database_heads != [repository_head]:
                    raise RuntimeError(
                        "Acceptance schemahead wijkt af: "
                        f"database={database_heads}, repository={[repository_head]}"
                    )

        if runtime_database != migrator_database:
            raise RuntimeError(
                "Runtime en migrator wijzen niet naar dezelfde testdatabase: "
                f"runtime={runtime_database}, migrator={migrator_database}"
            )
        if runtime_user == migrator_user:
            raise RuntimeError("Runtime- en migrator-role mogen niet dezelfde databasegebruiker zijn")
        if runtime_create:
            raise RuntimeError("Acceptance runtime-role heeft onverwacht schema CREATE")
        if not migrator_create:
            raise RuntimeError("Acceptance migrator mist schema CREATE authority")

        return {
            "datastore": "postgresql",
            "database": runtime_database,
            "runtime_user": runtime_user,
            "migrator_user": migrator_user,
            "runtime_create": runtime_create,
            "migrator_create": migrator_create,
            "alembic_head": repository_head,
            "database_heads": database_heads,
        }
    finally:
        runtime_engine.dispose()
        migration_engine.dispose()


def reset_postgresql_test_database() -> None:
    """Truncate all application tables while preserving Alembic lineage."""

    migration_engine = create_postgresql_migration_test_engine()
    try:
        with migration_engine.begin() as conn:
            tables = [
                name
                for name in inspect(conn).get_table_names(schema="public")
                if name != "alembic_version"
            ]
            if not tables:
                return
            preparer = conn.dialect.identifier_preparer
            table_sql = ", ".join(
                f"public.{preparer.quote(name)}" for name in sorted(tables)
            )
            conn.exec_driver_sql(
                f"TRUNCATE TABLE {table_sql} RESTART IDENTITY CASCADE"
            )
    finally:
        migration_engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate shared PostgreSQL acceptance boundary")
    parser.add_argument(
        "--skip-head",
        action="store_true",
        help="Validate runtime/migrator authority before Alembic has been applied.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    result = postgresql_acceptance_snapshot(require_alembic_head=not args.skip_head)
    print("REZZERV_POSTGRESQL_ACCEPTANCE_FOUNDATION")
    for key in (
        "datastore",
        "database",
        "runtime_user",
        "migrator_user",
        "runtime_create",
        "migrator_create",
        "alembic_head",
    ):
        print(f"{key}={result[key]}")
    print("POSTGRESQL_ACCEPTANCE_FOUNDATION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
