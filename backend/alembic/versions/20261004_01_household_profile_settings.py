"""Household profile, residents and personal display name.

Revision ID: 20261004_01
Revises: 20260930_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20261004_01"
down_revision = "20260930_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["auth", "shared"]


def upgrade() -> None:
    op.add_column("app_users", sa.Column("display_name", sa.Text(), nullable=True))

    op.create_table(
        "household_profiles",
        sa.Column("household_id", sa.Text(), primary_key=True),
        sa.Column("street", sa.Text(), nullable=True),
        sa.Column("house_number", sa.Text(), nullable=True),
        sa.Column("house_number_addition", sa.Text(), nullable=True),
        sa.Column("postal_code", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("country_code", sa.Text(), nullable=True),
        sa.Column("preferred_stores_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("shopping_interval_days", sa.Integer(), nullable=True),
        sa.Column("default_reserve_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "household_residents",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=True),
        sa.Column("resident_type", sa.Text(), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("age_band", sa.Text(), nullable=True),
        sa.Column("linked_user_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_household_residents_household",
        "household_residents",
        ["household_id"],
    )
    op.create_index(
        "uq_household_resident_linked_user",
        "household_residents",
        ["household_id", "linked_user_id"],
        unique=True,
        postgresql_where=sa.text("linked_user_id IS NOT NULL"),
        sqlite_where=sa.text("linked_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_household_resident_linked_user", table_name="household_residents")
    op.drop_index("ix_household_residents_household", table_name="household_residents")
    op.drop_table("household_residents")
    op.drop_table("household_profiles")
    op.drop_column("app_users", "display_name")
