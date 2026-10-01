"""Persist encrypted retailer account credentials and sync state.

Revision ID: 20260930_01
Revises: 20260926_03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260930_01"
down_revision = "20260926_03"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["receipt", "shared"]


def upgrade() -> None:
    op.create_table(
        "retailer_account_credentials",
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("credential_ciphertext", sa.Text(), nullable=False),
        sa.Column("known_receipt_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("household_id", "provider", name="pk_retailer_account_credentials"),
    )
    op.create_index(
        "ix_retailer_account_credentials_provider",
        "retailer_account_credentials",
        ["provider"],
    )


def downgrade() -> None:
    op.drop_index("ix_retailer_account_credentials_provider", table_name="retailer_account_credentials")
    op.drop_table("retailer_account_credentials")
