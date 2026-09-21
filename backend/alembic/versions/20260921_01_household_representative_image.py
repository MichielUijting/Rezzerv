"""Persist stable representative product images on household articles.

Revision ID: 20260921_01
Revises: 20260919_01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260921_01"
down_revision = "20260919_01"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    return {
        str(column.get("name") or "")
        for column in sa.inspect(bind).get_columns(table_name)
    }


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"postgresql", "sqlite"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    tables = set(sa.inspect(bind).get_table_names())
    if "household_articles" not in tables:
        raise RuntimeError(
            "Representative image migration requires household_articles"
        )

    columns = _columns(bind, "household_articles")
    if "representative_image_url" not in columns:
        op.add_column(
            "household_articles",
            sa.Column("representative_image_url", sa.Text(), nullable=True),
        )
    if "representative_image_global_product_id" not in columns:
        op.add_column(
            "household_articles",
            sa.Column(
                "representative_image_global_product_id",
                sa.Text(),
                nullable=True,
            ),
        )
    if "representative_image_gpc_brick_code" not in columns:
        op.add_column(
            "household_articles",
            sa.Column(
                "representative_image_gpc_brick_code",
                sa.Text(),
                nullable=True,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "household_articles" not in tables:
        return
    columns = _columns(bind, "household_articles")
    for column_name in (
        "representative_image_gpc_brick_code",
        "representative_image_global_product_id",
        "representative_image_url",
    ):
        if column_name in columns:
            op.drop_column("household_articles", column_name)
