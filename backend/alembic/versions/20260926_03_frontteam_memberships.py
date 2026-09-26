"""Persistent Frontteam membership administration.

Revision ID: 20260926_03
Revises: 20260926_02
"""
from alembic import op
import sqlalchemy as sa

revision = "20260926_03"
down_revision = "20260926_02"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["authorization", "shared"]


def upgrade() -> None:
    op.create_table(
        "frontteam_memberships",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.execute("""
        INSERT INTO frontteam_memberships(user_id, status)
        SELECT user_id, CASE WHEN active IS TRUE THEN 'active' ELSE 'inactive' END
        FROM auth_platform_user_roles
        WHERE role_key = 'platform.frontteam'
        ON CONFLICT(user_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("frontteam_memberships")
