"""Household-scoped Lidl import date window and incremental checkpoint.

Revision ID: 20261011_01
Revises: 20261005_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20261011_01"
down_revision = "20261005_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["receipt", "auth"]


def upgrade() -> None:
    op.create_table(
        "household_lidl_import_windows",
        sa.Column("household_id", sa.Text(), primary_key=True),
        sa.Column("from_date", sa.Date(), nullable=True),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("last_imported_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("household_lidl_import_windows")
