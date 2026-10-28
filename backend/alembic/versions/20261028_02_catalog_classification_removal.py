"""Reversible deactivation of article classifications, preserving prior audit."""
from alembic import op
import sqlalchemy as sa

revision = '20261028_02'
down_revision = '20261028_01'
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ['catalog', 'auth', 'shared']


def upgrade():
    # Additive migration: 20261028_01 may already have been applied locally.
    op.add_column(
        'global_product_shopify_classifications',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'global_product_shopify_history',
        sa.Column('action', sa.Text(), nullable=False, server_default='confirmed'),
    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text(
        'SELECT 1 FROM global_product_shopify_classifications '
        'WHERE is_active = FALSE LIMIT 1'
    )).first() or bind.execute(sa.text(
        "SELECT 1 FROM global_product_shopify_history "
        "WHERE action = 'removed' LIMIT 1"
    )).first():
        raise RuntimeError('Veilig gestopt: verwijderde artikelclassificaties en historie behouden.')
    op.drop_column('global_product_shopify_history', 'action')
    op.drop_column('global_product_shopify_classifications', 'is_active')
