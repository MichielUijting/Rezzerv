from __future__ import annotations

import gzip
from pathlib import Path

from sqlalchemy import create_engine, text

from app.services.external_article_product_link_service import (
    ensure_external_article_product_link_schema,
)
from app.services.receipt_lifecycle_foundation_service import (
    ensure_receipt_lifecycle_foundation_schema,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = (
    BACKEND_ROOT
    / "app"
    / "services"
    / "external_article_product_link_service.py"
)
SERVER_SESSION_SERVICE_PATH = (
    BACKEND_ROOT
    / "app"
    / "services"
    / "server_session_service.py"
)
RECEIPT_LIFECYCLE_SERVICE_PATH = (
    BACKEND_ROOT
    / "app"
    / "services"
    / "receipt_lifecycle_foundation_service.py"
)
MIGRATION_PATH = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "20260827_02_postgresql_application_schema.py"
)
SERVER_SESSION_MIGRATION_PATH = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "20260828_01_server_session_schema_authority.py"
)
RECEIPT_LIFECYCLE_MIGRATION_PATH = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "20260828_02_receipt_lifecycle_schema_authority.py"
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
RECEIPT_TEST_CONTRACT_PATH = (
    BACKEND_ROOT
    / "app"
    / "testing"
    / "receipt_lifecycle_contract.py"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _source_contract() -> None:
    service = SERVICE_PATH.read_text(encoding="utf-8")
    server_session_service = SERVER_SESSION_SERVICE_PATH.read_text(encoding="utf-8")
    receipt_service = RECEIPT_LIFECYCLE_SERVICE_PATH.read_text(encoding="utf-8")
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    server_session_migration = SERVER_SESSION_MIGRATION_PATH.read_text(encoding="utf-8")
    receipt_migration = RECEIPT_LIFECYCLE_MIGRATION_PATH.read_text(encoding="utf-8")
    runtime_preflight = RUNTIME_PREFLIGHT_PATH.read_text(encoding="utf-8")
    schema_preflight = SCHEMA_PREFLIGHT_PATH.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    test_contract = TEST_CONTRACT_PATH.read_text(encoding="utf-8")
    receipt_test_contract = RECEIPT_TEST_CONTRACT_PATH.read_text(encoding="utf-8")
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

    for forbidden in (
        "CREATE TABLE",
        "CREATE INDEX",
        "ALTER TABLE",
        "DROP TABLE",
        "PRAGMA ",
        "SQLITE_MASTER",
    ):
        _require(
            forbidden not in server_session_service.upper(),
            f"Production server-sessionservice bevat nog runtime schema-authority: {forbidden}",
        )
    _require(
        "def ensure_server_session_schema(conn: Connection) -> None:\n"
        "    \"\"\"Compatibility shim; Alembic owns the server_sessions schema.\"\"\"\n"
        "    del conn" in server_session_service,
        "Legacy server-session schema-hook is niet aantoonbaar inert",
    )
    _require(
        "revision: str = \"20260828_01\"" in server_session_migration
        and "down_revision: Union[str, None] = \"20260827_02\"" in server_session_migration,
        "Server-session authority revision heeft onverwachte lineage",
    )
    _require(
        "CREATE TABLE {table_name}" in server_session_migration
        and "idx_server_sessions_user_active" in server_session_migration,
        "Server-session Alembic revision bezit niet het volledige schema-contract",
    )
    _require(
        "_validate_postgresql(bind)" in server_session_migration,
        "Server-session authority revision valideert PostgreSQL niet fail-closed",
    )

    for forbidden in (
        "CREATE TABLE",
        "CREATE INDEX",
        "ALTER TABLE",
        "DROP TABLE",
        "CREATE TRIGGER",
        "DROP TRIGGER",
        "PRAGMA ",
        "SQLITE_MASTER",
    ):
        _require(
            forbidden not in receipt_service.upper(),
            f"Production receipt-lifecycleservice bevat nog runtime schema-authority: {forbidden}",
        )
    _require(
        "def ensure_receipt_lifecycle_foundation_schema(conn) -> None:\n"
        "    \"\"\"Compatibility shim; Alembic owns the receipt lifecycle schema.\"\"\"\n"
        "    del conn" in receipt_service,
        "Legacy receipt lifecycle schema-hook is niet aantoonbaar inert",
    )
    _require(
        "def ensure_explicit_approval_guard_trigger(conn) -> None:\n"
        "    \"\"\"Compatibility shim; Alembic owns the receipt approval guard trigger.\"\"\"\n"
        "    del conn" in receipt_service,
        "Legacy receipt approval-trigger hook is niet aantoonbaar inert",
    )
    _require(
        "def reconcile_receipt_lifecycle_foundation_data(conn)" in receipt_service
        and "def reconcile_explicit_receipt_approvals(" in receipt_service,
        "Receipt lifecycle datareconciliation is onverwacht verwijderd",
    )
    _require(
        "revision: str = \"20260828_02\"" in receipt_migration
        and "down_revision: Union[str, None] = \"20260828_01\"" in receipt_migration,
        "Receipt lifecycle authority revision heeft onverwachte lineage",
    )
    _require(
        "_validate_sqlite(bind)" in receipt_migration
        and "_validate_postgresql(bind)" in receipt_migration
        and "trg_receipt_tables_preserve_explicit_approval" in receipt_migration,
        "Receipt lifecycle authority revision valideert het schema niet fail-closed",
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
    for receipt_object in (
        "idx_receipt_tables_logical_receipt_key",
        "idx_receipt_table_lines_logical_line_key",
        "idx_receipt_tables_workflow_state",
        "uq_raw_receipts_household_hash",
        "trg_receipt_tables_preserve_explicit_approval",
    ):
        _require(
            receipt_object in baseline,
            f"Immutable schema baseline mist receipt lifecycle object: {receipt_object}",
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
    _require(
        "CREATE TRIGGER" in receipt_test_contract
        and "trg_receipt_tables_preserve_explicit_approval" in receipt_test_contract,
        "Geïsoleerde receipt lifecycle test bezit zijn eigen approval-triggerfixture niet",
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
        ensure_receipt_lifecycle_foundation_schema(conn)

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
        receipt_tables = conn.execute(
            text(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name IN ('raw_receipts', 'receipt_tables', 'receipt_table_lines')"
            )
        ).scalar_one()
        _require(
            receipt_tables == 0,
            "Legacy receipt lifecycle schema-hook heeft onverwacht schema aangemaakt",
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
        conn.execute(text("CREATE TABLE receipt_tables (id TEXT PRIMARY KEY)"))
        schema_before = tuple(
            conn.execute(
                text(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master "
                    "WHERE sql IS NOT NULL ORDER BY type, name"
                )
            ).all()
        )

        ensure_external_article_product_link_schema(conn)
        ensure_receipt_lifecycle_foundation_schema(conn)

        schema_after = tuple(
            conn.execute(
                text(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master "
                    "WHERE sql IS NOT NULL ORDER BY type, name"
                )
            ).all()
        )
        _require(
            schema_before == schema_after,
            "Legacy schema-hooks wijzigden bestaand schema",
        )


def main() -> None:
    _source_contract()
    _inert_legacy_hook_contract()
    print("SCHEMA_AUTHORITY_SOURCE_CONTRACT_GREEN")
    print("EXTERNAL_LINK_RUNTIME_DDL_REMOVED_GREEN")
    print("EXTERNAL_LINK_LEGACY_SCHEMA_HOOK_INERT_GREEN")
    print("SERVER_SESSION_RUNTIME_DDL_REMOVED_GREEN")
    print("SERVER_SESSION_LEGACY_SCHEMA_HOOK_INERT_GREEN")
    print("RECEIPT_LIFECYCLE_RUNTIME_DDL_REMOVED_GREEN")
    print("RECEIPT_LIFECYCLE_LEGACY_SCHEMA_HOOK_INERT_GREEN")
    print("SCHEMA_AUTHORITY_CUTOVER_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
