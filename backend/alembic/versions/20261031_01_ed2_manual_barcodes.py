"""Store user-confirmed ED2 GTIN evidence separately from verified OFF/GPC links.

No historical SQLite schema change. Does not change receipt/inventory consumers.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261031_01'
down_revision = '20261028_02'
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ['catalog', 'receipt', 'shared']


def upgrade() -> None:
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.create_table(
        'ed2_manual_barcodes',
        sa.Column('retailer_code', sa.String(128), nullable=False),
        sa.Column('receipt_text_normalized', sa.Text(), nullable=False),
        sa.Column('external_article_code', sa.String(256), nullable=False),
        sa.Column('gtin', sa.String(14), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('retailer_code', 'receipt_text_normalized', 'external_article_code',
                                name='pk_ed2_manual_barcodes'),
    )
    # The maintenance write barrier applies to every new PostgreSQL domain
    # table, including barcode-only evidence that can be shared across stores.
    bind = op.get_bind()
    schema = bind.execute(sa.text('SELECT current_schema()')).scalar_one()
    quoted = bind.dialect.identifier_preparer.quote_identifier
    bind.exec_driver_sql(
        'CREATE TRIGGER inhuis_maintenance_write_gate '
        'BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE '
        f'ON {quoted(schema)}.{quoted("ed2_manual_barcodes")} FOR EACH STATEMENT '
        f'EXECUTE FUNCTION {quoted(schema)}.inhuis_maintenance_write_barrier()'
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != 'postgresql':
        return
    count = op.get_bind().execute(sa.text('SELECT COUNT(*) FROM ed2_manual_barcodes')).scalar_one()
    if count:
        raise RuntimeError('Handmatig opgeslagen barcodes bestaan nog; veilig downgraden is niet mogelijk.')
    op.drop_table('ed2_manual_barcodes')
