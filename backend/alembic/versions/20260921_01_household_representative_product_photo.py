"""Add household-level representative Catalogus product for photos.

Revision ID: 20260921_01
Revises: 20260919_01

The relation stores a representative exact Catalogus product for one household
article. The image URL itself remains owned by global_products. GPC Brick is
persisted as the compatibility boundary used when the representative was chosen.
Existing rows are backfilled by runtime DML after Alembic has established the
schema, so schema authority remains Alembic-only.
"""
from __future__ import annotations

from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "20260921_01"
down_revision = "20260919_01"
branch_labels = None
depends_on = None

_TABLE = "household_article_representative_products"
_PRODUCT_INDEX = "idx_household_article_representative_product_global_product"
_BRICK_INDEX = "idx_household_article_representative_product_brick"


def _timestamp_type(dialect_name: str) -> sa.types.TypeEngine[Any]:
    if dialect_name == "postgresql":
        return sa.DateTime(timezone=True)
    return sa.DateTime()


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"postgresql", "sqlite"}:
        raise RuntimeError(
            f"Unsupported Rezzerv migration dialect: {bind.dialect.name}"
        )

    inspector = sa.inspect(bind)
    required = {
        "household_articles",
        "global_products",
        "global_product_gpc_bricks",
    }
    missing = required - set(inspector.get_table_names())
    if missing:
        raise RuntimeError(
            "Representative product migration requires canonical tables: "
            + ", ".join(sorted(missing))
        )

    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("household_article_id", sa.Text(), nullable=False),
            sa.Column("global_product_id", sa.Text(), nullable=False),
            sa.Column("brick_code", sa.String(length=8), nullable=False),
            sa.Column(
                "selection_source",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'automatic_same_brick'"),
            ),
            sa.Column(
                "created_at",
                _timestamp_type(bind.dialect.name),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                _timestamp_type(bind.dialect.name),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.PrimaryKeyConstraint("household_article_id"),
            sa.ForeignKeyConstraint(
                ["household_article_id"],
                ["household_articles.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["global_product_id"],
                ["global_products.id"],
            ),
        )

    inspector = sa.inspect(bind)
    indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes(_TABLE)
    }
    if _PRODUCT_INDEX not in indexes:
        op.create_index(
            _PRODUCT_INDEX,
            _TABLE,
            ["global_product_id"],
            unique=False,
        )
    if _BRICK_INDEX not in indexes:
        op.create_index(
            _BRICK_INDEX,
            _TABLE,
            ["brick_code"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
