"""Central automatic consumption types; no household or stock backfill."""
from alembic import op
import sqlalchemy as sa

revision = '20261023_01'
down_revision = '20261021_01'
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ['catalog', 'gpc', 'inventory', 'receipt']


def upgrade():
    op.create_table(
        'global_product_consumption_profiles',
        sa.Column('global_product_id', sa.Text(), sa.ForeignKey('global_products.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('classification_key', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('label', sa.Text(), nullable=True),
        sa.Column('facts_json', sa.Text(), nullable=False),
        sa.Column('profile_json', sa.Text(), nullable=False),
        sa.Column('source_fingerprint', sa.Text(), nullable=False),
        sa.Column('policy_version', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.CheckConstraint("status IN ('ready', 'pending')", name='ck_consumption_profile_status'),
    )
    op.create_index('idx_consumption_profile_key', 'global_product_consumption_profiles', ['classification_key'])


def downgrade():
    op.drop_index('idx_consumption_profile_key', table_name='global_product_consumption_profiles')
    op.drop_table('global_product_consumption_profiles')
