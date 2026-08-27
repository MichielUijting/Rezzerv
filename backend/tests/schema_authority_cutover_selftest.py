from __future__ import annotations

import gzip
from pathlib import Path

from sqlalchemy import create_engine, text

from app.services.external_article_product_link_service import (
    ensure_external_article_product_link_schema,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = (
    BACKEND_ROOT
    / "app"
    / "services"
    / "external_article_product_link_service.py"
)
MIGRATION_PATH = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "20260827_02_postgresql_application_schema.py"
)
BASELINE_PATH = BACKEND_ROOT / "alembic" / "baseline_sqlite.sql.gz"
RUNTIME_PREFLIGHT_PATH = BACKEND_ROOT / "app" / "runtime_preflight.py"
SCHEMA_PREFLIGHT_PATH = BACKEND_ROOT / "app" / "schema_migration_preflight.py"
DOCKERFILE_PATH = BACKEND_ROOT / "Dockerfile"
TEST_CONTRACT_PATH = (
    BACKEND_ROOT
    / "app"
    / "testing"
    / "external_article_product_link_contract.py"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _source_contract() -> None:
    service = SERVICE_PATH.read_text(encoding="utf-8")
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    runtime_preflight = RUNTIME_PREFLIGHT_PATH.read_text(encoding="utf-8")
    schema_preflight = SCHEMA_PREFLIGHT_PATH.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    test_contract = TEST_CONTRACT_PATH.read_text(encoding="utf-8")
    with gzip.open(BASELINE_PATH, "rt", encoding="utf-8") as handle:
        baseline = handle.read()

    _require(
        "CREATE TABLE" not in service.upper(),
        "Production external-linkservice bevat nog CREATE TABLE DDL",
    )
    _require(
        "CREATE INDEX" not in service.upper(),
        "Production external-linkservice bevat nog CREATE INDEX DDL",
    )
    _require(
        service.count("ensure_external_article_product_link_schema(conn)") == 1,
        "Legacy schema-hook mag alleen nog als inerte functiedefinitie bestaan",
    )
    _require(
        "del conn" in service,
        "Legacy schema-hook is niet aantoonbaar inert",
    )

    _require(
        "external_article_product_links" in migration,
        "PostgreSQL application migration mist external-link table contract",
    )
    for required_index in (
        "uq_external_article_product_links_code_confirmed",
        "uq_external_article_product_links_text_confirmed",
        "idx_external_article_product_links_product",
        "idx_external_article_product_links_candidate",
    ):
        _require(
            required_index in baseline,
            f"Immutable schema baseline mist external-link index: {required_index}",
        )

    _require(
        "run_schema_migration_preflight()" in runtime_preflight,
        "Runtime preflight voert schema-migratie niet uit",
    )
    _require(
        runtime_preflight.index("run_schema_migration_preflight()")
        < runtime_preflight.index("warm_receipt_image_preprocessing()"),
        "Schema-migratie moet vóór receipt runtime warmup lopen",
    )
    _require(
        "command.stamp(config, _SQLITE_BASELINE_REVISION)" in schema_preflight,
        "Bestaande gevalideerde SQLite kan niet veilig worden geadopteerd",
    )
    _require(
        "actual != expected" in schema_preflight,
        "SQLite adoption mist fail-closed baselinevergelijking",
    )
    _require(
        "COPY alembic.ini ./alembic.ini" in dockerfile
        and "COPY alembic ./alembic" in dockerfile,
        "Backend runtime image bevat de Alembic-keten niet",
    )
    _require(
        "CREATE TABLE external_article_product_links" in test_contract,
        "Geïsoleerde contracttest bezit zijn eigen external-link schemafixture niet",
    )


def _inert_legacy_hook_contract() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    with engine.begin() as conn:
        before_missing = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'external_article_product_links'
                """
            )
        ).scalar_one()
        _require(before_missing == 0, "Testdatabase begon niet schema-loos")

        ensure_external_article_product_link_schema(conn)

        after_missing = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'external_article_product_links'
                """
            )
        ).scalar_one()
        _require(
            after_missing == 0,
            "Legacy schema-hook heeft onverwacht schema aangemaakt",
        )

        conn.execute(
            text(
                """
                CREATE TABLE external_article_product_links (
                    id TEXT PRIMARY KEY
                )
                """
            )
        )
        schema_before = conn.execute(
            text(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'external_article_product_links'
                """
            )
        ).scalar_one()

        ensure_external_article_product_link_schema(conn)

        schema_after = conn.execute(
            text(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'external_article_product_links'
                """
            )
        ).scalar_one()
        _require(
            schema_before == schema_after,
            "Legacy schema-hook wijzigde bestaand schema",
        )


def main() -> None:
    _source_contract()
    _inert_legacy_hook_contract()
    print("SCHEMA_AUTHORITY_SOURCE_CONTRACT_GREEN")
    print("EXTERNAL_LINK_RUNTIME_DDL_REMOVED_GREEN")
    print("EXTERNAL_LINK_LEGACY_SCHEMA_HOOK_INERT_GREEN")
    print("SCHEMA_AUTHORITY_CUTOVER_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
