from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

import migration_foundation_selftest as foundation_test


HEAD_REVISION = "20260830_02"
RECEIPT_HOUSEHOLD_TABLES = ("receipt_sources", "raw_receipts", "receipt_tables")
MANUAL_SOURCE_TRIGGER = "trg_raw_receipts_ensure_manual_source"


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

    trigger = connection.execute(
        text(
            """
            SELECT t.tgname
            FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND c.relname = 'raw_receipts'
              AND t.tgname = :name
              AND NOT t.tgisinternal
            """
        ),
        {"name": MANUAL_SOURCE_TRIGGER},
    ).first()
    if trigger is None:
        raise AssertionError("PostgreSQL manual-upload source invariant trigger missing")
    print("POSTGRESQL_RECEIPT_HOUSEHOLD_AUTHORITY_GREEN")


def main() -> None:
    foundation_test.HEAD_REVISION = HEAD_REVISION
    foundation_test.main()

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
