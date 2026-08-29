"""Move article-group request schema authority to Alembic.

Revision ID: 20260829_02
Revises: 20260829_01
Create Date: 2026-08-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_02"
down_revision: Union[str, None] = "20260829_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ARTICLE_GROUPS = "article_groups"
_HOUSEHOLD_ARTICLES = "household_articles"
_ARTICLE_GROUP_COLUMNS = {
    "id",
    "household_id",
    "name",
    "normalized_name",
    "status",
    "sort_order",
    "created_at",
    "updated_at",
}
_INDEXES = {
    "idx_article_groups_household_name": (
        _ARTICLE_GROUPS,
        ("household_id", "normalized_name"),
    ),
    "idx_household_articles_article_group": (
        _HOUSEHOLD_ARTICLES,
        ("article_group_id",),
    ),
}


def _ensure_index(bind: sa.engine.Connection, name: str, table: str, columns: tuple[str, ...]) -> None:
    indexes = {
        str(index.get("name") or ""): index
        for index in sa.inspect(bind).get_indexes(table)
    }
    existing = indexes.get(name)
    if existing is None:
        op.create_index(name, table, list(columns), unique=False)
        return
    actual_columns = tuple(str(column or "") for column in (existing.get("column_names") or ()))
    if actual_columns != columns or bool(existing.get("unique")):
        raise RuntimeError(
            f"Bestaande index {name} wijkt af: expected={columns!r}/False "
            f"actual={actual_columns!r}/{bool(existing.get('unique'))}"
        )


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_ARTICLE_GROUPS):
        raise RuntimeError("article_groups ontbreekt")
    columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns(_ARTICLE_GROUPS)
    }
    missing = _ARTICLE_GROUP_COLUMNS - columns
    if missing:
        raise RuntimeError(f"article_groups mist canonical kolommen: {sorted(missing)}")
    if not inspector.has_table(_HOUSEHOLD_ARTICLES):
        raise RuntimeError("household_articles ontbreekt")
    household_columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns(_HOUSEHOLD_ARTICLES)
    }
    if "article_group_id" not in household_columns:
        raise RuntimeError("household_articles.article_group_id ontbreekt")
    for name, (table, expected_columns) in _INDEXES.items():
        indexes = {
            str(index.get("name") or ""): index
            for index in inspector.get_indexes(table)
        }
        index = indexes.get(name)
        actual_columns = tuple(str(column or "") for column in ((index or {}).get("column_names") or ()))
        if not index or actual_columns != expected_columns or bool(index.get("unique")):
            raise RuntimeError(f"Canonical article-group index {name} wijkt af")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    inspector = sa.inspect(bind)
    if not inspector.has_table(_ARTICLE_GROUPS):
        op.create_table(
            _ARTICLE_GROUPS,
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("household_id", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("normalized_name", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=True, server_default=sa.text("'active'")),
            sa.Column("sort_order", sa.Integer(), nullable=True, server_default=sa.text("0")),
            sa.Column("created_at", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.Text(), nullable=True),
        )
    else:
        existing = {
            str(column.get("name") or "")
            for column in inspector.get_columns(_ARTICLE_GROUPS)
        }
        required_legacy = {"id", "household_id", "name", "normalized_name"}
        missing_legacy = required_legacy - existing
        if missing_legacy:
            raise RuntimeError(
                f"article_groups legacy contract mist kolommen: {sorted(missing_legacy)}"
            )
        additions = {
            "status": sa.Column("status", sa.Text(), nullable=True, server_default=sa.text("'active'")),
            "sort_order": sa.Column("sort_order", sa.Integer(), nullable=True, server_default=sa.text("0")),
            "created_at": sa.Column("created_at", sa.Text(), nullable=True),
            "updated_at": sa.Column("updated_at", sa.Text(), nullable=True),
        }
        for column_name, column in additions.items():
            if column_name not in existing:
                op.add_column(_ARTICLE_GROUPS, column)

    bind.execute(
        sa.text(
            "UPDATE article_groups SET status = 'active' "
            "WHERE COALESCE(status, 'active') <> 'active'"
        )
    )

    inspector = sa.inspect(bind)
    if not inspector.has_table(_HOUSEHOLD_ARTICLES):
        raise RuntimeError("household_articles ontbreekt; kan article-group authority niet adopteren")
    household_columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns(_HOUSEHOLD_ARTICLES)
    }
    if "article_group_id" not in household_columns:
        op.add_column(
            _HOUSEHOLD_ARTICLES,
            sa.Column("article_group_id", sa.Text(), nullable=True),
        )

    for name, (table, columns) in _INDEXES.items():
        _ensure_index(bind, name, table, columns)

    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The article-group request schema-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
