"""Correct receipt household authority and canonical manual-upload sources.

Revision ID: 20260830_02
Revises: 20260830_01
Create Date: 2026-08-30
"""
from __future__ import annotations

from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_02"
down_revision: Union[str, None] = "20260830_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RECEIPT_HOUSEHOLD_TABLES = ("receipt_sources", "raw_receipts", "receipt_tables")
_HOUSEHOLD_REGISTRY = "household_registry"
_LEGACY_HOUSEHOLDS = "households"
_MANUAL_SOURCE_TYPE = "manual_upload"
_MANUAL_SOURCE_LABEL = "Handmatige upload"
_SQLITE_MANUAL_SOURCE_TRIGGER = "trg_raw_receipts_ensure_manual_source"
_POSTGRESQL_MANUAL_SOURCE_TRIGGER = "trg_raw_receipts_ensure_manual_source"
_POSTGRESQL_MANUAL_SOURCE_FUNCTION = "rezzerv_ensure_raw_receipt_manual_source"
_SQLITE_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def _quote_sqlite_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _household_fk(bind: sa.engine.Connection, table_name: str) -> dict[str, Any]:
    matches = [
        fk
        for fk in sa.inspect(bind).get_foreign_keys(table_name)
        if tuple(str(value) for value in (fk.get("constrained_columns") or ()))
        == ("household_id",)
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"{table_name}.household_id vereist exact één FK; actual={matches!r}"
        )
    fk = matches[0]
    referred_columns = tuple(str(value) for value in (fk.get("referred_columns") or ()))
    if referred_columns != ("id",):
        raise RuntimeError(
            f"{table_name}.household_id FK verwijst niet naar id: {fk!r}"
        )
    return fk


def _assert_household_values_are_registered(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    required = {_HOUSEHOLD_REGISTRY, "receipt_sources", "raw_receipts", "receipt_tables"}
    missing = required - tables
    if missing:
        raise RuntimeError(f"Receipt household authority mist tabellen: {sorted(missing)}")

    for table_name in _RECEIPT_HOUSEHOLD_TABLES:
        row = bind.execute(
            sa.text(
                f"""
                SELECT child.household_id
                FROM {table_name} AS child
                LEFT JOIN household_registry AS registry ON registry.id = child.household_id
                WHERE child.household_id IS NOT NULL
                  AND registry.id IS NULL
                LIMIT 1
                """
            )
        ).first()
        if row is not None:
            raise RuntimeError(
                f"{table_name}.household_id bevat niet-geregistreerde household: {row[0]!r}"
            )


def _assert_missing_sources_are_manual_upload_only(bind: sa.engine.Connection) -> None:
    rows = bind.execute(
        sa.text(
            """
            SELECT raw.id, raw.household_id, raw.source_id
            FROM raw_receipts AS raw
            LEFT JOIN receipt_sources AS source ON source.id = raw.source_id
            WHERE raw.source_id IS NOT NULL
              AND source.id IS NULL
            ORDER BY raw.id
            """
        )
    ).all()
    invalid = [
        (str(row[0]), str(row[1]), str(row[2]))
        for row in rows
        if str(row[2]) != f"{str(row[1])}-manual-upload"
    ]
    if invalid:
        raise RuntimeError(
            "Onbekende ontbrekende receipt source-parent(s); recovery geweigerd: "
            f"{invalid[:10]!r}"
        )


def _ensure_manual_sources(bind: sa.engine.Connection) -> int:
    household_ids = [
        str(value)
        for value in bind.execute(
            sa.text("SELECT id FROM household_registry ORDER BY id")
        ).scalars()
    ]
    inserted = 0
    for household_id in household_ids:
        source_id = f"{household_id}-manual-upload"
        exists = bind.execute(
            sa.text("SELECT 1 FROM receipt_sources WHERE id = :id LIMIT 1"),
            {"id": source_id},
        ).first()
        if exists:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO receipt_sources (
                    id, household_id, type, label, source_path, is_active
                ) VALUES (
                    :id, :household_id, :type, :label, NULL, :is_active
                )
                """
            ),
            {
                "id": source_id,
                "household_id": household_id,
                "type": _MANUAL_SOURCE_TYPE,
                "label": _MANUAL_SOURCE_LABEL,
                "is_active": True,
            },
        )
        inserted += 1
    return inserted


def _sqlite_receipt_dependent_triggers(
    bind: sa.engine.Connection,
) -> list[tuple[str, str]]:
    """Capture only triggers attached to or referencing the rebuilt receipt tables.

    SQLite batch-alter recreates a table under a temporary name. SQLite validates
    triggers in other tables during the final rename, so a trigger such as the
    receipt approval guard (owned by receipt_tables but reading raw_receipts)
    must be removed for the complete multi-table rebuild and restored afterwards.
    """
    rows = bind.exec_driver_sql(
        """
        SELECT name, tbl_name, sql
        FROM sqlite_master
        WHERE type = 'trigger'
          AND sql IS NOT NULL
        ORDER BY name
        """
    ).all()
    receipt_tables = set(_RECEIPT_HOUSEHOLD_TABLES)
    result: list[tuple[str, str]] = []
    for name, table_name, sql in rows:
        trigger_name = str(name)
        trigger_table = str(table_name)
        statement = str(sql or "").strip()
        normalized = statement.lower()
        if trigger_table in receipt_tables or any(
            table_name.lower() in normalized for table_name in receipt_tables
        ):
            result.append((trigger_name, statement))
    return result


def _drop_sqlite_triggers(
    bind: sa.engine.Connection,
    triggers: Sequence[tuple[str, str]],
) -> None:
    for trigger_name, _statement in triggers:
        bind.exec_driver_sql(
            f"DROP TRIGGER IF EXISTS {_quote_sqlite_identifier(trigger_name)}"
        )


def _restore_sqlite_triggers(
    bind: sa.engine.Connection,
    triggers: Sequence[tuple[str, str]],
) -> None:
    for _trigger_name, statement in triggers:
        bind.exec_driver_sql(statement)


def _replace_sqlite_household_fk(bind: sa.engine.Connection, table_name: str) -> None:
    fk = _household_fk(bind, table_name)
    referred = str(fk.get("referred_table") or "")
    if referred == _HOUSEHOLD_REGISTRY:
        return
    if referred != _LEGACY_HOUSEHOLDS:
        raise RuntimeError(
            f"Onverwachte legacy household parent voor {table_name}: {referred!r}"
        )

    old_name = f"fk_{table_name}_household_id_{_LEGACY_HOUSEHOLDS}"
    new_name = f"fk_{table_name}_household_id_{_HOUSEHOLD_REGISTRY}"
    with op.batch_alter_table(
        table_name,
        recreate="always",
        naming_convention=_SQLITE_NAMING_CONVENTION,
    ) as batch:
        batch.drop_constraint(old_name, type_="foreignkey")
        batch.create_foreign_key(
            new_name,
            _HOUSEHOLD_REGISTRY,
            ["household_id"],
            ["id"],
        )


def _replace_postgresql_household_fk(bind: sa.engine.Connection, table_name: str) -> None:
    fk = _household_fk(bind, table_name)
    referred = str(fk.get("referred_table") or "")
    if referred == _HOUSEHOLD_REGISTRY:
        return
    if referred != _LEGACY_HOUSEHOLDS:
        raise RuntimeError(
            f"Onverwachte legacy household parent voor {table_name}: {referred!r}"
        )
    constraint_name = str(fk.get("name") or "").strip()
    if not constraint_name:
        raise RuntimeError(f"PostgreSQL FK zonder naam voor {table_name}.household_id")
    op.drop_constraint(constraint_name, table_name, type_="foreignkey")
    op.create_foreign_key(
        f"fk_{table_name}_household_id_{_HOUSEHOLD_REGISTRY}",
        table_name,
        _HOUSEHOLD_REGISTRY,
        ["household_id"],
        ["id"],
    )


def _create_manual_source_trigger(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql(f'DROP TRIGGER IF EXISTS "{_SQLITE_MANUAL_SOURCE_TRIGGER}"')
        bind.exec_driver_sql(
            f"""
            CREATE TRIGGER "{_SQLITE_MANUAL_SOURCE_TRIGGER}"
            BEFORE INSERT ON raw_receipts
            WHEN NEW.source_id = NEW.household_id || '-manual-upload'
            BEGIN
                INSERT OR IGNORE INTO receipt_sources (
                    id, household_id, type, label, source_path, is_active
                ) VALUES (
                    NEW.source_id, NEW.household_id, '{_MANUAL_SOURCE_TYPE}',
                    '{_MANUAL_SOURCE_LABEL}', NULL, 1
                );
            END
            """
        )
        return

    bind.exec_driver_sql(
        f"""
        CREATE OR REPLACE FUNCTION {_POSTGRESQL_MANUAL_SOURCE_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.source_id = NEW.household_id || '-manual-upload' THEN
                INSERT INTO receipt_sources (
                    id, household_id, type, label, source_path, is_active
                ) VALUES (
                    NEW.source_id, NEW.household_id, '{_MANUAL_SOURCE_TYPE}',
                    '{_MANUAL_SOURCE_LABEL}', NULL, TRUE
                )
                ON CONFLICT (id) DO NOTHING;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    bind.exec_driver_sql(
        f'DROP TRIGGER IF EXISTS "{_POSTGRESQL_MANUAL_SOURCE_TRIGGER}" ON raw_receipts'
    )
    bind.exec_driver_sql(
        f"""
        CREATE TRIGGER "{_POSTGRESQL_MANUAL_SOURCE_TRIGGER}"
        BEFORE INSERT ON raw_receipts
        FOR EACH ROW
        EXECUTE FUNCTION {_POSTGRESQL_MANUAL_SOURCE_FUNCTION}()
        """
    )


def _assert_final_contract(bind: sa.engine.Connection) -> None:
    for table_name in _RECEIPT_HOUSEHOLD_TABLES:
        fk = _household_fk(bind, table_name)
        if str(fk.get("referred_table") or "") != _HOUSEHOLD_REGISTRY:
            raise RuntimeError(f"{table_name}.household_id is niet canonical household_registry-owned")

    missing_manual = bind.execute(
        sa.text(
            """
            SELECT registry.id
            FROM household_registry AS registry
            LEFT JOIN receipt_sources AS source
              ON source.id = registry.id || '-manual-upload'
             AND source.household_id = registry.id
             AND source.type = :type
            WHERE source.id IS NULL
            LIMIT 1
            """
        ),
        {"type": _MANUAL_SOURCE_TYPE},
    ).first()
    if missing_manual is not None:
        raise RuntimeError(
            f"Canonical manual-upload source ontbreekt voor household {missing_manual[0]!r}"
        )

    if bind.dialect.name == "sqlite":
        trigger = bind.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=? AND tbl_name='raw_receipts' LIMIT 1",
            (_SQLITE_MANUAL_SOURCE_TRIGGER,),
        ).first()
        if trigger is None:
            raise RuntimeError("SQLite manual-upload source invariant trigger ontbreekt")
        fk_rows = bind.exec_driver_sql("PRAGMA foreign_key_check").all()
        if fk_rows:
            raise RuntimeError(f"SQLite foreign_key_check faalt na receipt authority cutover: {fk_rows[:10]!r}")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    _assert_household_values_are_registered(bind)
    _assert_missing_sources_are_manual_upload_only(bind)
    _ensure_manual_sources(bind)

    if bind.dialect.name == "sqlite":
        dependent_triggers = _sqlite_receipt_dependent_triggers(bind)
        _drop_sqlite_triggers(bind, dependent_triggers)
        for table_name in _RECEIPT_HOUSEHOLD_TABLES:
            _replace_sqlite_household_fk(bind, table_name)
        _restore_sqlite_triggers(bind, dependent_triggers)
    else:
        for table_name in _RECEIPT_HOUSEHOLD_TABLES:
            _replace_postgresql_household_fk(bind, table_name)

    _create_manual_source_trigger(bind)
    _assert_final_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "Receipt household authority recovery is intentionally non-destructive and cannot be downgraded"
    )
