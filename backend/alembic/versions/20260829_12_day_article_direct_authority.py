"""Move day-article and Direct-location schema authority to Alembic.

Revision ID: 20260829_12
Revises: 20260829_11
Create Date: 2026-08-29
"""
from __future__ import annotations

from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_12"
down_revision: Union[str, None] = "20260829_11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ARTICLES = "household_articles"
_SPACES = "spaces"
_SUBLOCATIONS = "sublocations"
_EVENTS = "day_article_processing_events"
_SPACE_SYSTEM_INDEX = "idx_spaces_household_system_key"
_SUBLOCATION_SYSTEM_INDEX = "idx_sublocations_space_system_key"
_EVENT_ARTICLE_INDEX = "idx_day_article_events_article"
_EVENT_UNIQUE = "uq_day_article_processing_events_idempotency"

_ARTICLE_COLUMNS = {
    "id",
    "household_id",
    "naam",
    "default_inventory_handling",
    "inventory_handling_updated_at",
    "inventory_handling_updated_by_user_id",
}
_SPACE_COLUMNS = {"id", "naam", "household_id", "system_key", "protected"}
_SUBLOCATION_COLUMNS = {"id", "naam", "space_id", "system_key", "protected"}
_EVENT_COLUMNS = {
    "id",
    "household_id",
    "household_article_id",
    "idempotency_key",
    "event_type",
    "quantity",
    "space_id",
    "sublocation_id",
    "actor_user_id",
    "created_at",
}


def _columns(bind: sa.engine.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    return {
        str(column.get("name") or ""): column
        for column in sa.inspect(bind).get_columns(table_name)
    }


def _timestamp_type(dialect_name: str) -> sa.types.TypeEngine[Any]:
    if dialect_name == "postgresql":
        return sa.DateTime(timezone=True)
    return sa.Text()


def _protected_type(dialect_name: str) -> sa.types.TypeEngine[Any]:
    if dialect_name == "postgresql":
        return sa.Boolean()
    return sa.Integer()


def _normalize_postgresql_timestamp(
    bind: sa.engine.Connection,
    table_name: str,
    column_name: str,
    *,
    nullable: bool,
    default_current_timestamp: bool,
) -> None:
    column = _columns(bind, table_name)[column_name]
    if isinstance(column["type"], sa.DateTime) and bool(
        getattr(column["type"], "timezone", False)
    ):
        return
    bind.exec_driver_sql(
        f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" DROP DEFAULT'
    )
    if nullable:
        using = (
            f"CASE WHEN NULLIF(trim(\"{column_name}\"::text), '') IS NULL "
            f"THEN NULL ELSE \"{column_name}\"::text::timestamptz END"
        )
    else:
        using = f'"{column_name}"::text::timestamptz'
    bind.exec_driver_sql(
        f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" '
        f"TYPE TIMESTAMPTZ USING {using}"
    )
    if default_current_timestamp:
        bind.exec_driver_sql(
            f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" '
            "SET DEFAULT CURRENT_TIMESTAMP"
        )


def _normalize_postgresql_protected(
    bind: sa.engine.Connection,
    table_name: str,
) -> None:
    column = _columns(bind, table_name)["protected"]
    if isinstance(column["type"], sa.Boolean):
        bind.execute(
            sa.text(f'UPDATE "{table_name}" SET protected = FALSE WHERE protected IS NULL')
        )
    else:
        bind.execute(
            sa.text(f'UPDATE "{table_name}" SET protected = 0 WHERE protected IS NULL')
        )
        bind.exec_driver_sql(
            f'ALTER TABLE "{table_name}" ALTER COLUMN protected DROP DEFAULT'
        )
        bind.exec_driver_sql(
            f'ALTER TABLE "{table_name}" ALTER COLUMN protected TYPE BOOLEAN '
            "USING CASE "
            "WHEN protected::text IN ('1', 't', 'true', 'TRUE') THEN TRUE "
            "WHEN protected::text IN ('0', 'f', 'false', 'FALSE') THEN FALSE "
            "ELSE FALSE END"
        )
    bind.exec_driver_sql(
        f'ALTER TABLE "{table_name}" ALTER COLUMN protected SET DEFAULT FALSE'
    )
    bind.exec_driver_sql(
        f'ALTER TABLE "{table_name}" ALTER COLUMN protected SET NOT NULL'
    )


def _ensure_article_columns(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_ARTICLES):
        raise RuntimeError("household_articles ontbreekt; dagartikel-authority kan niet worden geadopteerd")
    columns = _columns(bind, _ARTICLES)
    required_base = {"id", "household_id", "naam"}
    missing_base = required_base - set(columns)
    if missing_base:
        raise RuntimeError(
            f"household_articles mist basiscontract: {sorted(missing_base)}"
        )
    if "default_inventory_handling" not in columns:
        op.add_column(
            _ARTICLES,
            sa.Column(
                "default_inventory_handling",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'STOCK'"),
            ),
        )
    if "inventory_handling_updated_at" not in columns:
        op.add_column(
            _ARTICLES,
            sa.Column(
                "inventory_handling_updated_at",
                _timestamp_type(bind.dialect.name),
                nullable=True,
            ),
        )
    if "inventory_handling_updated_by_user_id" not in columns:
        op.add_column(
            _ARTICLES,
            sa.Column("inventory_handling_updated_by_user_id", sa.Text(), nullable=True),
        )

    bind.execute(
        sa.text(
            """
            UPDATE household_articles
            SET default_inventory_handling = 'STOCK'
            WHERE default_inventory_handling IS NULL
               OR trim(default_inventory_handling) = ''
            """
        )
    )
    invalid = bind.execute(
        sa.text(
            """
            SELECT DISTINCT default_inventory_handling
            FROM household_articles
            WHERE default_inventory_handling NOT IN ('STOCK', 'DIRECT_CONSUMPTION')
            ORDER BY default_inventory_handling
            """
        )
    ).all()
    if invalid:
        raise RuntimeError(
            "household_articles bevat ongeldige default_inventory_handling waarden: "
            f"{[row[0] for row in invalid]!r}"
        )

    if bind.dialect.name == "postgresql":
        _normalize_postgresql_timestamp(
            bind,
            _ARTICLES,
            "inventory_handling_updated_at",
            nullable=True,
            default_current_timestamp=False,
        )
        op.alter_column(
            _ARTICLES,
            "default_inventory_handling",
            existing_type=sa.Text(),
            nullable=False,
            server_default=sa.text("'STOCK'"),
        )


def _ensure_location_columns(bind: sa.engine.Connection, table_name: str) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        raise RuntimeError(f"{table_name} ontbreekt; Direct-location authority kan niet worden geadopteerd")
    columns = _columns(bind, table_name)
    required_base = {"id", "naam"}
    if table_name == _SPACES:
        required_base.add("household_id")
    else:
        required_base.add("space_id")
    missing_base = required_base - set(columns)
    if missing_base:
        raise RuntimeError(f"{table_name} mist basiscontract: {sorted(missing_base)}")
    if "system_key" not in columns:
        op.add_column(table_name, sa.Column("system_key", sa.Text(), nullable=True))
    if "protected" not in columns:
        default = sa.text("false") if bind.dialect.name == "postgresql" else sa.text("0")
        op.add_column(
            table_name,
            sa.Column(
                "protected",
                _protected_type(bind.dialect.name),
                nullable=False,
                server_default=default,
            ),
        )
    elif bind.dialect.name == "postgresql":
        _normalize_postgresql_protected(bind, table_name)
    else:
        invalid = bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table_name} "
                "WHERE protected IS NULL OR protected NOT IN (0, 1)"
            )
        ).scalar_one()
        if int(invalid or 0):
            raise RuntimeError(f"{table_name}.protected bevat niet-canonical waarden")


def _ensure_partial_unique_index(
    bind: sa.engine.Connection,
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    indexes = {
        str(index.get("name") or ""): index
        for index in sa.inspect(bind).get_indexes(table_name)
    }
    index = indexes.get(index_name)
    if index is None:
        kwargs: dict[str, object] = {}
        if bind.dialect.name == "sqlite":
            kwargs["sqlite_where"] = sa.text("system_key IS NOT NULL")
        else:
            kwargs["postgresql_where"] = sa.text("system_key IS NOT NULL")
        op.create_index(index_name, table_name, columns, unique=True, **kwargs)
        return
    if not bool(index.get("unique")) or tuple(index.get("column_names") or ()) != tuple(columns):
        raise RuntimeError(f"{index_name} wijkt af van het canonical Direct-location contract")


def _event_unique_sets(bind: sa.engine.Connection) -> set[tuple[str, ...]]:
    inspector = sa.inspect(bind)
    unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(_EVENTS)
    }
    unique_sets.update(
        tuple(index.get("column_names") or ())
        for index in inspector.get_indexes(_EVENTS)
        if bool(index.get("unique"))
    )
    return unique_sets


def _ensure_event_table(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_EVENTS):
        op.create_table(
            _EVENTS,
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("household_id", sa.Text(), nullable=False),
            sa.Column("household_article_id", sa.Text(), nullable=False),
            sa.Column("idempotency_key", sa.Text(), nullable=False),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("quantity", sa.Numeric(), nullable=False),
            sa.Column("space_id", sa.Text(), nullable=False),
            sa.Column("sublocation_id", sa.Text(), nullable=False),
            sa.Column("actor_user_id", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                _timestamp_type(bind.dialect.name),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint(
                "household_id",
                "idempotency_key",
                "event_type",
                name=_EVENT_UNIQUE,
            ),
            sa.CheckConstraint(
                "event_type IN ('RECEIPT', 'DIRECT_CONSUMPTION')",
                name="ck_day_article_processing_events_type",
            ),
        )
    else:
        columns = _columns(bind, _EVENTS)
        missing = _EVENT_COLUMNS - set(columns)
        if missing:
            raise RuntimeError(
                f"day_article_processing_events mist canonical kolommen: {sorted(missing)}"
            )
        invalid = bind.execute(
            sa.text(
                """
                SELECT DISTINCT event_type
                FROM day_article_processing_events
                WHERE event_type NOT IN ('RECEIPT', 'DIRECT_CONSUMPTION')
                ORDER BY event_type
                """
            )
        ).all()
        if invalid:
            raise RuntimeError(
                "day_article_processing_events bevat ongeldige event_type waarden: "
                f"{[row[0] for row in invalid]!r}"
            )
        if bind.dialect.name == "postgresql":
            _normalize_postgresql_timestamp(
                bind,
                _EVENTS,
                "created_at",
                nullable=False,
                default_current_timestamp=True,
            )
        if ("household_id", "idempotency_key", "event_type") not in _event_unique_sets(bind):
            raise RuntimeError(
                "day_article_processing_events mist de canonical idempotency unique constraint"
            )

    indexes = {
        str(index.get("name") or ""): index
        for index in sa.inspect(bind).get_indexes(_EVENTS)
    }
    article_index = indexes.get(_EVENT_ARTICLE_INDEX)
    expected_columns = ("household_id", "household_article_id", "created_at")
    if article_index is None:
        op.create_index(_EVENT_ARTICLE_INDEX, _EVENTS, list(expected_columns), unique=False)
    elif bool(article_index.get("unique")) or tuple(article_index.get("column_names") or ()) != expected_columns:
        raise RuntimeError(f"{_EVENT_ARTICLE_INDEX} wijkt af van het canonical dagartikelcontract")


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    for table_name in (_ARTICLES, _SPACES, _SUBLOCATIONS, _EVENTS):
        if not inspector.has_table(table_name):
            raise RuntimeError(f"Canonical dagartikel/Direct-tabel ontbreekt: {table_name}")

    contracts = {
        _ARTICLES: _ARTICLE_COLUMNS,
        _SPACES: _SPACE_COLUMNS,
        _SUBLOCATIONS: _SUBLOCATION_COLUMNS,
        _EVENTS: _EVENT_COLUMNS,
    }
    for table_name, required in contracts.items():
        missing = required - set(_columns(bind, table_name))
        if missing:
            raise RuntimeError(f"{table_name} mist canonical kolommen: {sorted(missing)}")

    _ensure_partial_unique_index(
        bind,
        _SPACES,
        _SPACE_SYSTEM_INDEX,
        ["household_id", "system_key"],
    )
    _ensure_partial_unique_index(
        bind,
        _SUBLOCATIONS,
        _SUBLOCATION_SYSTEM_INDEX,
        ["space_id", "system_key"],
    )

    event_indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes(_EVENTS)
    }
    event_index = event_indexes.get(_EVENT_ARTICLE_INDEX)
    if not event_index or tuple(event_index.get("column_names") or ()) != (
        "household_id",
        "household_article_id",
        "created_at",
    ):
        raise RuntimeError(f"Canonical dagartikelindex ontbreekt: {_EVENT_ARTICLE_INDEX}")
    if ("household_id", "idempotency_key", "event_type") not in _event_unique_sets(bind):
        raise RuntimeError("Canonical dagartikel-idempotency constraint ontbreekt")

    if bind.dialect.name == "postgresql":
        for table_name in (_SPACES, _SUBLOCATIONS):
            protected = _columns(bind, table_name)["protected"]
            if not isinstance(protected["type"], sa.Boolean):
                raise RuntimeError(
                    f"{table_name}.protected moet BOOLEAN zijn; actual={protected['type']}"
                )
        for table_name, column_name in (
            (_ARTICLES, "inventory_handling_updated_at"),
            (_EVENTS, "created_at"),
        ):
            column = _columns(bind, table_name)[column_name]
            if not isinstance(column["type"], sa.DateTime) or not bool(
                getattr(column["type"], "timezone", False)
            ):
                raise RuntimeError(
                    f"{table_name}.{column_name} moet TIMESTAMPTZ zijn; actual={column['type']}"
                )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    _ensure_article_columns(bind)
    _ensure_location_columns(bind, _SPACES)
    _ensure_location_columns(bind, _SUBLOCATIONS)
    _ensure_partial_unique_index(
        bind,
        _SPACES,
        _SPACE_SYSTEM_INDEX,
        ["household_id", "system_key"],
    )
    _ensure_partial_unique_index(
        bind,
        _SUBLOCATIONS,
        _SUBLOCATION_SYSTEM_INDEX,
        ["space_id", "system_key"],
    )
    _ensure_event_table(bind)
    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The day-article/Direct schema-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
