"""Platform-wide configurable mobile Startpagina welcome text.

Revision ID: 20260926_01
Revises: 20260925_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260926_01"
down_revision = "20260925_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["shared"]

def upgrade() -> None:
    op.create_table(
        "platform_home_settings",
        sa.Column("setting_key", sa.Text(), primary_key=True),
        sa.Column("setting_value", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

def downgrade() -> None:
    op.drop_table("platform_home_settings")
