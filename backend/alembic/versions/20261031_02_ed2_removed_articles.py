"""Mark hidden Externe databases 2 article identities without changing receipt sources.

The registry is platform scoped and records exact presented identities. Soft-deleting
a related global product is a separate, guarded transaction in the domain service.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261031_02'
down_revision = '20261031_01'
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ['catalog', 'receipt', 'shared']


def upgrade() -> None:
    op.create_table(
        'ed2_removed_articles',
        sa.Column('retailer_code', sa.String(128), nullable=False),
        sa.Column('receipt_text', sa.Text(), nullable=False),
        sa.Column('external_article_code', sa.String(256), nullable=False),
        sa.Column('removed_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint(
            'retailer_code', 'receipt_text', 'external_article_code',
            name='pk_ed2_removed_articles',
        ),
    )
    if op.get_bind().dialect.name != 'postgresql':
        return
    bind = op.get_bind()
    schema = bind.execute(sa.text('SELECT current_schema()')).scalar_one()
    quoted = bind.dialect.identifier_preparer.quote_identifier
    bind.exec_driver_sql(
        'CREATE TRIGGER inhuis_maintenance_write_gate '
        'BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE '
        f'ON {quoted(schema)}.{quoted("ed2_removed_articles")} FOR EACH STATEMENT '
        f'EXECUTE FUNCTION {quoted(schema)}.inhuis_maintenance_write_barrier()'
    )


def downgrade() -> None:
    count = op.get_bind().execute(sa.text('SELECT COUNT(*) FROM ed2_removed_articles')).scalar_one()
    if count:
        raise RuntimeError('Er zijn verwijderde ED2-artikelen; veilig downgraden is niet mogelijk.')
    op.drop_table('ed2_removed_articles')
