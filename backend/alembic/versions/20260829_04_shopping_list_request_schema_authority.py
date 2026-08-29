"""Move shopping-list request schema under Alembic authority.

Revision ID: 20260829_04
Revises: 20260829_03
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260829_04"
down_revision: Union[str, None] = "20260829_03"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


SHOPPING_LIST_COLUMNS = {
    "id",
    "household_id",
    "status",
    "created_at",
    "completed_at",
    "completed_by",
}
SHOPPING_ITEM_CORE_COLUMNS = {
    "id",
    "shopping_list_id",
    "household_id",
    "article_name",
    "source_type",
    "quantity",
    "volume",
    "unit",
    "note",
    "checked",
    "created_at",
    "updated_at",
}
SHOPPING_ITEM_EXTENSION_COLUMNS = {
    "article_group_name": sa.Text(),
    "product_type_name": sa.Text(),
    "source_id": sa.Text(),
    "size": sa.Text(),
}


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind, table_name: str) -> set[str]:
    return {
        str(column["name"])
        for column in sa.inspect(bind).get_columns(table_name)
    }


def _index_names(bind, table_name: str) -> set[str]:
    return {
        str(index["name"])
        for index in sa.inspect(bind).get_indexes(table_name)
        if index.get("name")
    }


def _require_columns(bind, table_name: str, required: set[str]) -> None:
    missing = required - _column_names(bind, table_name)
    if missing:
        raise RuntimeError(
            f"Cannot adopt {table_name}: missing required columns: "
            + ", ".join(sorted(missing))
        )


def _ensure_shopping_lists(bind) -> None:
    if "shopping_lists" not in _table_names(bind):
        op.create_table(
            "shopping_lists",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("household_id", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("completed_at", sa.Text(), nullable=True),
            sa.Column("completed_by", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "status IN ('active', 'completed')",
                name="ck_shopping_lists_status",
            ),
        )
    else:
        columns = _column_names(bind, "shopping_lists")
        core = {"id", "household_id", "status", "created_at"}
        _require_columns(bind, "shopping_lists", core)
        if "completed_at" not in columns:
            op.add_column(
                "shopping_lists",
                sa.Column("completed_at", sa.Text(), nullable=True),
            )
        if "completed_by" not in columns:
            op.add_column(
                "shopping_lists",
                sa.Column("completed_by", sa.Text(), nullable=True),
            )

    _require_columns(bind, "shopping_lists", SHOPPING_LIST_COLUMNS)

    # Historical databases can predate the one-active-list invariant. Keep
    # the newest active list per household active and preserve older lists as
    # completed history before the partial unique index is created.
    op.execute(
        sa.text(
            """
            UPDATE shopping_lists
            SET status = 'completed',
                completed_at = COALESCE(completed_at, created_at),
                completed_by = COALESCE(completed_by, 'ALEMBIC_BACKFILL')
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY household_id
                            ORDER BY created_at DESC, id DESC
                        ) AS active_rank
                    FROM shopping_lists
                    WHERE status = 'active'
                ) ranked
                WHERE active_rank > 1
            )
            """
        )
    )

    indexes = _index_names(bind, "shopping_lists")
    if "ux_shopping_lists_household_active" not in indexes:
        active_where = sa.text("status = 'active'")
        op.create_index(
            "ux_shopping_lists_household_active",
            "shopping_lists",
            ["household_id"],
            unique=True,
            postgresql_where=active_where,
            sqlite_where=active_where,
        )


def _ensure_shopping_list_items(bind) -> None:
    if "shopping_list_items" not in _table_names(bind):
        op.create_table(
            "shopping_list_items",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("shopping_list_id", sa.Text(), nullable=False),
            sa.Column("household_id", sa.Text(), nullable=False),
            sa.Column("article_name", sa.Text(), nullable=False),
            sa.Column("article_group_name", sa.Text(), nullable=True),
            sa.Column("product_type_name", sa.Text(), nullable=True),
            sa.Column(
                "source_type",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'manual'"),
            ),
            sa.Column("source_id", sa.Text(), nullable=True),
            sa.Column("quantity", sa.Numeric(), nullable=True),
            sa.Column("volume", sa.Numeric(), nullable=True),
            sa.Column("unit", sa.Text(), nullable=True),
            sa.Column("size", sa.Text(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column(
                "checked",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(
                ["shopping_list_id"],
                ["shopping_lists.id"],
                name="fk_shopping_list_items_list",
            ),
        )
    else:
        _require_columns(bind, "shopping_list_items", SHOPPING_ITEM_CORE_COLUMNS)
        columns = _column_names(bind, "shopping_list_items")
        for column_name, column_type in SHOPPING_ITEM_EXTENSION_COLUMNS.items():
            if column_name not in columns:
                op.add_column(
                    "shopping_list_items",
                    sa.Column(column_name, column_type, nullable=True),
                )
                columns.add(column_name)

    required = SHOPPING_ITEM_CORE_COLUMNS | set(SHOPPING_ITEM_EXTENSION_COLUMNS)
    _require_columns(bind, "shopping_list_items", required)

    indexes = _index_names(bind, "shopping_list_items")
    if "idx_shopping_list_items_active" not in indexes:
        op.create_index(
            "idx_shopping_list_items_active",
            "shopping_list_items",
            ["household_id", "shopping_list_id", "checked", "article_name"],
            unique=False,
        )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_shopping_lists(bind)
    _ensure_shopping_list_items(bind)


def downgrade() -> None:
    # Adoption migration: an existing installation may have owned these
    # tables and indexes before Alembic. Do not destructively guess ownership
    # on downgrade.
    pass
