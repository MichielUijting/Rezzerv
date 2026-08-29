"""Fail-closed Alembic adoption/upgrade before Rezzerv runtime imports.

Fresh databases are upgraded to Alembic head. Existing unversioned SQLite
runtime databases are adopted only after their schema is proven byte-for-byte
equal to the immutable PR2a baseline. Alembic may use MIGRATION_DATABASE_URL,
while normal runtime access remains bound to DATABASE_URL.
"""
from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.db import engine
from app.migration_db import migration_engine


_SQLITE_BASELINE_REVISION = "20260827_01"
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ALEMBIC_CONFIG = _BACKEND_ROOT / "alembic.ini"
_SQLITE_BASELINE = _BACKEND_ROOT / "alembic" / "baseline_sqlite.sql.gz"


def _config() -> Config:
    if not _ALEMBIC_CONFIG.exists():
        raise RuntimeError(
            f"Alembic-config ontbreekt in runtime image: {_ALEMBIC_CONFIG}"
        )
    return Config(str(_ALEMBIC_CONFIG))


def _sqlite_schema_dump(conn) -> str:
    rows = conn.exec_driver_sql(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE sql IS NOT NULL
          AND name NOT LIKE 'sqlite_%'
          AND name <> 'alembic_version'
        ORDER BY
          CASE type
            WHEN 'table' THEN 0
            WHEN 'view' THEN 1
            WHEN 'index' THEN 2
            WHEN 'trigger' THEN 3
            ELSE 4
          END,
          name
        """
    ).all()

    statements: list[str] = []
    for object_type, name, table_name, sql in rows:
        normalized_sql = str(sql or "").strip().rstrip(";")
        if not normalized_sql:
            continue
        statements.append(f"-- {object_type}: {name} (table={table_name})")
        statements.append(normalized_sql + ";")
        statements.append("")
    return "\n".join(statements).rstrip() + "\n"


def _baseline_sqlite_schema() -> str:
    if not _SQLITE_BASELINE.exists():
        raise RuntimeError(
            f"Immutable SQLite-baseline ontbreekt in runtime image: {_SQLITE_BASELINE}"
        )
    with gzip.open(_SQLITE_BASELINE, "rt", encoding="utf-8") as handle:
        return handle.read()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sqlite_has_alembic_version(conn) -> bool:
    return bool(
        conn.exec_driver_sql(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'alembic_version'
            LIMIT 1
            """
        ).first()
    )


def _sqlite_has_application_schema(conn) -> bool:
    return bool(
        conn.exec_driver_sql(
            """
            SELECT 1
            FROM sqlite_master
            WHERE sql IS NOT NULL
              AND name NOT LIKE 'sqlite_%'
              AND name <> 'alembic_version'
            LIMIT 1
            """
        ).first()
    )


def _postgresql_has_alembic_version(conn) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'alembic_version'
                LIMIT 1
                """
            )
        ).first()
    )


def _postgresql_has_application_schema(conn) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name <> 'alembic_version'
                LIMIT 1
                """
            )
        ).first()
    )


def _prepare_sqlite(config: Config) -> str:
    with migration_engine.connect() as conn:
        has_application_schema = _sqlite_has_application_schema(conn)
        has_version = _sqlite_has_alembic_version(conn)

        if has_application_schema and not has_version:
            actual = _sqlite_schema_dump(conn)
            expected = _baseline_sqlite_schema()
            if actual != expected:
                raise RuntimeError(
                    "Bestaande SQLite-runtime wijkt af van de immutable Alembic-"
                    "baseline; automatische adoption is geweigerd. "
                    f"expected_sha256={_sha256(expected)}; "
                    f"actual_sha256={_sha256(actual)}"
                )

    if has_application_schema and not has_version:
        command.stamp(config, _SQLITE_BASELINE_REVISION)
        command.upgrade(config, "head")
        return "sqlite-validated-stamped-upgraded"

    command.upgrade(config, "head")
    return "sqlite-upgraded"


def _prepare_postgresql(config: Config) -> str:
    with migration_engine.connect() as conn:
        has_application_schema = _postgresql_has_application_schema(conn)
        has_version = _postgresql_has_alembic_version(conn)

    if has_application_schema and not has_version:
        raise RuntimeError(
            "Bestaand PostgreSQL-applicatieschema zonder Alembic-history wordt "
            "niet automatisch geadopteerd"
        )

    command.upgrade(config, "head")
    return "postgresql-upgraded"


def _expected_head(config: Config) -> str:
    heads = tuple(ScriptDirectory.from_config(config).get_heads())
    if len(heads) != 1:
        raise RuntimeError(f"Rezzerv vereist exact één Alembic-head; gevonden: {heads!r}")
    return str(heads[0])


def _runtime_revision() -> str:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    revisions = tuple(str(value or "").strip() for value in rows if str(value or "").strip())
    if len(revisions) != 1:
        raise RuntimeError(
            "Runtime-database heeft geen eenduidige Alembic-head: "
            f"revisions={revisions!r}"
        )
    return revisions[0]


def validate_runtime_schema_authority(config: Config) -> str:
    if engine.dialect.name != migration_engine.dialect.name:
        raise RuntimeError(
            "Migration- en runtime-datastore gebruiken verschillende dialecten: "
            f"migration={migration_engine.dialect.name}; runtime={engine.dialect.name}"
        )
    expected = _expected_head(config)
    actual = _runtime_revision()
    if actual != expected:
        raise RuntimeError(
            "Runtime-database staat niet op de canonical Alembic-head: "
            f"expected={expected}; actual={actual}"
        )
    return actual


def run_schema_migration_preflight() -> dict[str, str]:
    """Migrate through the migration connection, then validate runtime access."""
    config = _config()
    dialect = migration_engine.dialect.name

    if dialect == "sqlite":
        action = _prepare_sqlite(config)
    elif dialect == "postgresql":
        action = _prepare_postgresql(config)
    else:
        raise RuntimeError(
            f"Unsupported Rezzerv migration-preflight dialect: {dialect}"
        )

    revision = validate_runtime_schema_authority(config)
    result = {"dialect": dialect, "action": action, "revision": revision}
    print(f"Schema migration preflight: {result}", flush=True)
    return result


if __name__ == "__main__":
    run_schema_migration_preflight()
