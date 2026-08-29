"""Move residual GPC assignment and translation schema authority to Alembic.

Revision ID: 20260829_11
Revises: 20260829_10
Create Date: 2026-08-29
"""
from __future__ import annotations

from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_11"
down_revision: Union[str, None] = "20260829_10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ASSIGNMENT_TABLE = "global_product_gpc_bricks"
_SUPPRESSION_TABLE = "global_product_gpc_migration_suppressions"
_TRANSLATION_TABLE = "gpc_translations"
_TRANSLATION_RUN_TABLE = "gpc_translation_import_runs"

_ASSIGNMENT_COLUMNS = {
    "global_product_id",
    "brick_code",
    "assignment_source",
    "confidence",
    "migrated_from",
    "updated_at",
}
_SUPPRESSION_COLUMNS = {"global_product_id", "created_at"}
_TRANSLATION_COLUMNS = {
    "entity_type",
    "entity_code",
    "language_code",
    "translated_text",
    "translation_source",
    "reviewed",
    "updated_at",
}
_TRANSLATION_RUN_COLUMNS = {
    "id",
    "source_name",
    "source_sha256",
    "language_code",
    "imported_at",
    "status",
    "row_count",
    "message",
}


def _inspector(bind: sa.engine.Connection) -> sa.Inspector:
    return sa.inspect(bind)


def _column_map(bind: sa.engine.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    return {
        str(column.get("name") or ""): column
        for column in _inspector(bind).get_columns(table_name)
    }


def _timestamp_type(dialect_name: str) -> sa.types.TypeEngine[Any]:
    if dialect_name == "postgresql":
        return sa.DateTime(timezone=True)
    return sa.Text()


def _create_or_adopt_assignment_tables(bind: sa.engine.Connection) -> None:
    if not _inspector(bind).has_table(_ASSIGNMENT_TABLE):
        op.create_table(
            _ASSIGNMENT_TABLE,
            sa.Column("global_product_id", sa.Text(), primary_key=True),
            sa.Column("brick_code", sa.String(length=8), nullable=False),
            sa.Column(
                "assignment_source",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'manual_catalog_detail'"),
            ),
            sa.Column(
                "confidence",
                sa.Float(),
                nullable=False,
                server_default=sa.text("1.0"),
            ),
            sa.Column("migrated_from", sa.Text(), nullable=True),
            sa.Column(
                "updated_at",
                _timestamp_type(bind.dialect.name),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["global_product_id"], ["global_products.id"]),
            sa.ForeignKeyConstraint(["brick_code"], ["gpc_bricks.brick_code"]),
        )
    else:
        columns = _column_map(bind, _ASSIGNMENT_TABLE)
        if "assignment_source" not in columns:
            op.add_column(
                _ASSIGNMENT_TABLE,
                sa.Column(
                    "assignment_source",
                    sa.Text(),
                    nullable=False,
                    server_default=sa.text("'manual_catalog_detail'"),
                ),
            )
        columns = _column_map(bind, _ASSIGNMENT_TABLE)
        if "confidence" not in columns:
            op.add_column(
                _ASSIGNMENT_TABLE,
                sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
            )
        columns = _column_map(bind, _ASSIGNMENT_TABLE)
        if "migrated_from" not in columns:
            op.add_column(_ASSIGNMENT_TABLE, sa.Column("migrated_from", sa.Text(), nullable=True))

    if not _inspector(bind).has_table(_SUPPRESSION_TABLE):
        op.create_table(
            _SUPPRESSION_TABLE,
            sa.Column("global_product_id", sa.Text(), primary_key=True),
            sa.Column(
                "created_at",
                _timestamp_type(bind.dialect.name),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["global_product_id"], ["global_products.id"]),
        )


def _create_or_adopt_translation_tables(bind: sa.engine.Connection) -> None:
    if not _inspector(bind).has_table(_TRANSLATION_TABLE):
        op.create_table(
            _TRANSLATION_TABLE,
            sa.Column("entity_type", sa.String(length=30), nullable=False),
            sa.Column("entity_code", sa.String(length=8), nullable=False),
            sa.Column("language_code", sa.String(length=12), nullable=False),
            sa.Column("translated_text", sa.Text(), nullable=False),
            sa.Column("translation_source", sa.Text(), nullable=False),
            sa.Column("reviewed", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("updated_at", _timestamp_type(bind.dialect.name), nullable=False),
            sa.PrimaryKeyConstraint("entity_type", "entity_code", "language_code"),
        )

    if not _inspector(bind).has_table(_TRANSLATION_RUN_TABLE):
        op.create_table(
            _TRANSLATION_RUN_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("source_name", sa.Text(), nullable=False),
            sa.Column("source_sha256", sa.String(length=64), nullable=False),
            sa.Column("language_code", sa.String(length=12), nullable=False),
            sa.Column("imported_at", _timestamp_type(bind.dialect.name), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
        )


def _ensure_index(
    bind: sa.engine.Connection,
    *,
    table_name: str,
    index_name: str,
    columns: tuple[str, ...],
) -> None:
    indexes = {
        str(index.get("name") or ""): index
        for index in _inspector(bind).get_indexes(table_name)
    }
    existing = indexes.get(index_name)
    if existing is None:
        op.create_index(index_name, table_name, list(columns), unique=False)
        return
    if tuple(existing.get("column_names") or ()) != columns or bool(existing.get("unique")):
        raise RuntimeError(f"{index_name} wijkt af van het canonical GPC-indexcontract")


def _validate_table(bind: sa.engine.Connection, table_name: str, required_columns: set[str]) -> None:
    inspector = _inspector(bind)
    if not inspector.has_table(table_name):
        raise RuntimeError(f"Canonical GPC-tabel ontbreekt: {table_name}")
    missing = required_columns - set(_column_map(bind, table_name))
    if missing:
        raise RuntimeError(f"{table_name} mist canonical kolommen: {sorted(missing)}")


def _validate_contract(bind: sa.engine.Connection) -> None:
    _validate_table(bind, _ASSIGNMENT_TABLE, _ASSIGNMENT_COLUMNS)
    _validate_table(bind, _SUPPRESSION_TABLE, _SUPPRESSION_COLUMNS)
    _validate_table(bind, _TRANSLATION_TABLE, _TRANSLATION_COLUMNS)
    _validate_table(bind, _TRANSLATION_RUN_TABLE, _TRANSLATION_RUN_COLUMNS)

    assignment_pk = tuple(
        _inspector(bind).get_pk_constraint(_ASSIGNMENT_TABLE).get("constrained_columns") or ()
    )
    if assignment_pk != ("global_product_id",):
        raise RuntimeError(f"{_ASSIGNMENT_TABLE} heeft onjuiste primary key: {assignment_pk!r}")
    translation_pk = tuple(
        _inspector(bind).get_pk_constraint(_TRANSLATION_TABLE).get("constrained_columns") or ()
    )
    if translation_pk != ("entity_type", "entity_code", "language_code"):
        raise RuntimeError(f"{_TRANSLATION_TABLE} heeft onjuiste primary key: {translation_pk!r}")

    if bind.dialect.name == "postgresql":
        for table_name, column_name in (
            (_ASSIGNMENT_TABLE, "updated_at"),
            (_SUPPRESSION_TABLE, "created_at"),
            (_TRANSLATION_TABLE, "updated_at"),
            (_TRANSLATION_RUN_TABLE, "imported_at"),
        ):
            column = _column_map(bind, table_name)[column_name]
            column_type = column["type"]
            if not isinstance(column_type, sa.DateTime) or not bool(getattr(column_type, "timezone", False)):
                raise RuntimeError(f"{table_name}.{column_name} moet TIMESTAMPTZ zijn; actual={column_type}")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    for required_table in ("global_products", "gpc_bricks", "product_inventory_groups", "gpc_product_groups"):
        if not _inspector(bind).has_table(required_table):
            raise RuntimeError(f"Eerdere GPC schema-authority ontbreekt: {required_table}")

    _create_or_adopt_assignment_tables(bind)
    _create_or_adopt_translation_tables(bind)
    _ensure_index(
        bind,
        table_name=_ASSIGNMENT_TABLE,
        index_name="idx_global_product_gpc_brick_code",
        columns=("brick_code",),
    )
    _ensure_index(
        bind,
        table_name=_TRANSLATION_TABLE,
        index_name="idx_gpc_translation_language",
        columns=("language_code", "entity_type"),
    )
    _ensure_index(
        bind,
        table_name="gpc_product_groups",
        index_name="idx_gpc_product_groups_hierarchy",
        columns=("gpc_family_code", "gpc_class_code", "gpc_brick_code"),
    )
    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "20260829_11 is a non-destructive GPC schema-authority cutover and cannot be downgraded"
    )
