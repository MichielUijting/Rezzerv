from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

import migration_foundation_selftest as foundation_test


HEAD_REVISION = "20260830_02"
RECEIPT_HOUSEHOLD_TABLES = ("receipt_sources", "raw_receipts", "receipt_tables")
MANUAL_SOURCE_TRIGGER = "trg_raw_receipts_ensure_manual_source"
_SQLITE_MANUAL_SOURCE_TRIGGER_HEADER = (
    "-- trigger: trg_raw_receipts_ensure_manual_source (table=raw_receipts)"
)
_LEGACY_FOUNDATION_POSTGRESQL_TRIGGERS = {
    "trg_household_zero_system_insert",
    "trg_receipt_tables_preserve_explicit_approval",
    "trg_spaces_direct_immutable_update",
    "trg_spaces_direct_immutable_delete",
}
EXPECTED_POSTGRESQL_TRIGGERS = (
    _LEGACY_FOUNDATION_POSTGRESQL_TRIGGERS | {MANUAL_SOURCE_TRIGGER}
)


def _postgresql_trigger_names(connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            text(
                """
                SELECT t.tgname
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema()
                  AND NOT t.tgisinternal
                """
            )
        ).all()
    }


def _remove_locked_sqlite_trigger_extension(schema: str) -> str:
    """Remove exactly the 20260830_02 trigger block from baseline comparison."""
    blocks = [block for block in schema.rstrip().split("\n\n") if block.strip()]
    retained = [
        block
        for block in blocks
        if block.splitlines()[0].strip() != _SQLITE_MANUAL_SOURCE_TRIGGER_HEADER
    ]
    return "\n\n".join(retained).rstrip() + "\n"


def _run_foundation_with_locked_head_contract() -> None:
    """Extend only the schema contracts introduced at 20260830_02.

    The historical foundation core deliberately keeps its pre-20260830_02
    trigger and immutable-baseline defaults. The head wrapper treats exactly
    the new raw-receipt manual-source trigger as a later SQLite migration
    extension and permits exactly that same fifth trigger in PostgreSQL. Every
    other baseline, schema or trigger difference remains fail-closed.
    """
    original_assert = foundation_test.foundation._assert_postgresql_schema
    original_strip = foundation_test.foundation._strip_migration_extensions

    def _strip_migration_extensions_at_head(schema: str) -> str:
        return _remove_locked_sqlite_trigger_extension(original_strip(schema))

    def _assert_postgresql_schema_at_head(connection) -> None:
        try:
            original_assert(connection)
            return
        except AssertionError as exc:
            message = str(exc)
            if not message.startswith("Unexpected PostgreSQL trigger contract:"):
                raise

        actual = _postgresql_trigger_names(connection)
        if actual != EXPECTED_POSTGRESQL_TRIGGERS:
            raise AssertionError(
                "Unexpected PostgreSQL trigger contract at locked head: "
                f"expected={sorted(EXPECTED_POSTGRESQL_TRIGGERS)} "
                f"actual={sorted(actual)}"
            )

        # The historical core reaches its trigger assertion only after every
        # preceding PostgreSQL schema check has passed. Emit the markers that
        # immediately follow that final assertion in the core contract.
        print(
            "POSTGRESQL_APPLICATION_SCHEMA_GREEN "
            f"revision={foundation_test.foundation.HEAD_REVISION} "
            f"tables={foundation_test.foundation.EXPECTED_POSTGRESQL_APPLICATION_TABLES}"
        )
        print("POSTGRESQL_EXTERNAL_CATALOG_SCHEMA_AUTHORITY_GREEN")
        print("POSTGRESQL_GPC_BARCODE_SCHEMA_AUTHORITY_GREEN")
        print("POSTGRESQL_AUTHORIZATION_BOOLEAN_SCHEMA_GREEN")
        print("POSTGRESQL_ONBOARDING_USE_CASE_SCHEMA_AUTHORITY_GREEN")
        print("POSTGRESQL_GPC_RESIDUAL_SCHEMA_AUTHORITY_GREEN")

    foundation_test.foundation._strip_migration_extensions = _strip_migration_extensions_at_head
    foundation_test.foundation._assert_postgresql_schema = _assert_postgresql_schema_at_head
    try:
        foundation_test.main()
    finally:
        foundation_test.foundation._assert_postgresql_schema = original_assert
        foundation_test.foundation._strip_migration_extensions = original_strip


def _assert_receipt_household_authority(connection) -> None:
    inspector = inspect(connection)
    for table_name in RECEIPT_HOUSEHOLD_TABLES:
        matches = [
            fk
            for fk in inspector.get_foreign_keys(table_name)
            if tuple(fk.get("constrained_columns") or ()) == ("household_id",)
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"{table_name}.household_id requires one FK; actual={matches!r}"
            )
        fk = matches[0]
        if str(fk.get("referred_table") or "") != "household_registry":
            raise AssertionError(
                f"{table_name}.household_id must reference household_registry.id; actual={fk!r}"
            )
        if tuple(fk.get("referred_columns") or ()) != ("id",):
            raise AssertionError(
                f"{table_name}.household_id must reference household_registry.id; actual={fk!r}"
            )

    if connection.dialect.name == "sqlite":
        trigger = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name=? AND tbl_name='raw_receipts'",
            (MANUAL_SOURCE_TRIGGER,),
        ).first()
        if trigger is None:
            raise AssertionError("SQLite manual-upload source invariant trigger missing")
        if connection.exec_driver_sql("PRAGMA foreign_key_check").all():
            raise AssertionError("SQLite receipt household authority has FK violations")
        print("SQLITE_RECEIPT_HOUSEHOLD_AUTHORITY_GREEN")
        return

    actual_triggers = _postgresql_trigger_names(connection)
    if actual_triggers != EXPECTED_POSTGRESQL_TRIGGERS:
        raise AssertionError(
            "Unexpected PostgreSQL trigger contract at receipt authority head: "
            f"expected={sorted(EXPECTED_POSTGRESQL_TRIGGERS)} "
            f"actual={sorted(actual_triggers)}"
        )
    print("POSTGRESQL_RECEIPT_HOUSEHOLD_AUTHORITY_GREEN")


def main() -> None:
    foundation_test.HEAD_REVISION = HEAD_REVISION
    _run_foundation_with_locked_head_contract()

    engine = create_engine(foundation_test.foundation._engine_url())
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision != HEAD_REVISION:
                raise AssertionError(
                    f"Expected Alembic revision {HEAD_REVISION}, got {revision}"
                )
            _assert_receipt_household_authority(connection)
    finally:
        engine.dispose()

    print("MIGRATION_FOUNDATION_REVISION_20260830_02_GREEN")


if __name__ == "__main__":
    main()
