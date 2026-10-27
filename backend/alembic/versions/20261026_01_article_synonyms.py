"""Central manually confirmed synonyms; no product or household merge."""
from alembic import op
import sqlalchemy as sa

revision = '20261026_01'
down_revision = '20261023_02'
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ['catalog', 'auth', 'shared']


def upgrade():
    op.create_table(
        'article_synonym_links',
        sa.Column('left_product_id', sa.Text(), sa.ForeignKey('global_products.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('right_product_id', sa.Text(), sa.ForeignKey('global_products.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('confirmed_by', sa.Text(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('source_fingerprint', sa.Text(), nullable=False),
        sa.Column('method', sa.Text(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.CheckConstraint('left_product_id < right_product_id', name='ck_article_synonym_pair_order'),
        sa.CheckConstraint('score >= 0 AND score <= 1', name='ck_article_synonym_score'),
    )
    op.create_index('idx_article_synonym_right', 'article_synonym_links', ['right_product_id'])
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        schema = conn.execute(sa.text('SELECT current_schema()')).scalar_one()
        quoted = conn.dialect.identifier_preparer.quote_identifier(schema)
        conn.exec_driver_sql(
            'CREATE TRIGGER inhuis_maintenance_write_gate '
            'BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE '
            f'ON {quoted}.article_synonym_links FOR EACH STATEMENT EXECUTE FUNCTION '
            f'{quoted}.inhuis_maintenance_write_barrier()'
        )


def downgrade():
    op.drop_index('idx_article_synonym_right', table_name='article_synonym_links')
    op.drop_table('article_synonym_links')
