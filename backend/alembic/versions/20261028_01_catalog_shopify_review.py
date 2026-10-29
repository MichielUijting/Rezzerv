"""Separate Shopify review authority, unrelated to GS1 or household groups."""
from alembic import op
import sqlalchemy as sa

revision = '20261028_01'
down_revision = '20261027_01'
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ['catalog', 'auth', 'shared']

def guard(table):
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    schema = bind.execute(sa.text('SELECT current_schema()')).scalar_one()
    quote = bind.dialect.identifier_preparer.quote_identifier
    bind.exec_driver_sql(
        'CREATE TRIGGER inhuis_maintenance_write_gate '
        'BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE '
        f'ON {quote(schema)}.{quote(table)} FOR EACH STATEMENT '
        f'EXECUTE FUNCTION {quote(schema)}.inhuis_maintenance_write_barrier()'
    )

def upgrade():
    op.create_table(
        'global_product_shopify_classifications',
        sa.Column('global_product_id', sa.Text(), sa.ForeignKey('global_products.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('shopify_id', sa.Text(), nullable=False),
        sa.Column('shopify_path', sa.Text(), nullable=False),
        sa.Column('taxonomy_version', sa.Text(), nullable=False),
        sa.Column('barcode_at_confirmation', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('confirmed_by', sa.Text(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint('version > 0', name='ck_shopify_review_version_positive'),
    )
    op.create_table(
        'global_product_shopify_history',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('global_product_id', sa.Text(), nullable=False),
        sa.Column('shopify_id', sa.Text(), nullable=False),
        sa.Column('shopify_path', sa.Text(), nullable=False),
        sa.Column('taxonomy_version', sa.Text(), nullable=False),
        sa.Column('barcode_at_confirmation', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('confirmed_by', sa.Text(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_shopify_history_product', 'global_product_shopify_history', ['global_product_id', 'confirmed_at'])
    guard('global_product_shopify_classifications')
    guard('global_product_shopify_history')

def downgrade():
    bind = op.get_bind()
    for table in ('global_product_shopify_classifications', 'global_product_shopify_history'):
        if bind.execute(sa.text(f'SELECT 1 FROM {table} LIMIT 1')).first():
            raise RuntimeError('Veilig gestopt: Shopify-classificaties of wijzigingshistorie bestaan.')
    op.drop_index('idx_shopify_history_product', table_name='global_product_shopify_history')
    op.drop_table('global_product_shopify_history')
    op.drop_table('global_product_shopify_classifications')
