"""Persist external product image URLs in OFF candidates and Catalogus products.

Revision ID: 20260919_01
Revises: 20260918_01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260919_01"
down_revision = "20260918_01"
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
    required = {"global_products", "external_product_candidates"}
    missing = required - tables
    if missing:
        raise RuntimeError(
            "Catalog image migration requires canonical tables: "
            + ", ".join(sorted(missing))
        )

    if "image_url" not in _columns(bind, "global_products"):
        op.add_column("global_products", sa.Column("image_url", sa.Text(), nullable=True))

    if "image_url" not in _columns(bind, "external_product_candidates"):
        op.add_column(
            "external_product_candidates",
            sa.Column("image_url", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "external_product_candidates" in tables and "image_url" in _columns(bind, "external_product_candidates"):
        op.drop_column("external_product_candidates", "image_url")
    if "global_products" in tables and "image_url" in _columns(bind, "global_products"):
        op.drop_column("global_products", "image_url")
