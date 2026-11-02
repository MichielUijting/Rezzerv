"""Add isolated CBS ECOICOPv2 classification authority, without importing unverified data.

This is additive: existing Shopify, GS1, catalog, retail and inventory rows
are not touched. Reference data and confirmed assignments are populated only
through later, explicitly reviewed authority operations.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261102_01'
down_revision = '20261031_02'
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ['catalog', 'auth', 'shared']


def _guard(table: str) -> None:
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


def upgrade() -> None:
    op.create_table(
        'cbs_ecoicop_categories',
        sa.Column('cbs_code', sa.String(6), nullable=False),
        sa.Column('reference_version', sa.Text(), nullable=False),
        sa.Column('name_nl', sa.Text(), nullable=False),
        sa.Column('parent_code', sa.String(6), nullable=True),
        sa.Column('level', sa.SmallInteger(), nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('source_sha256', sa.String(64), nullable=False),
        sa.Column('scope_notes', sa.Text(), nullable=False, server_default=''),
        sa.PrimaryKeyConstraint('cbs_code', 'reference_version', name='pk_cbs_ecoicop_categories'),
        sa.ForeignKeyConstraint(
            ['parent_code', 'reference_version'],
            ['cbs_ecoicop_categories.cbs_code', 'cbs_ecoicop_categories.reference_version'],
            name='fk_cbs_ecoicop_parent',
            deferrable=True,
            initially='DEFERRED',
        ),
        sa.CheckConstraint(
            "cbs_code ~ '^[0-9]{6}
        sa.CheckConstraint('level BETWEEN 1 AND 5', name='ck_cbs_level_valid'),
        sa.CheckConstraint('length(trim(name_nl)) > 0', name='ck_cbs_name_required'),
        sa.CheckConstraint('length(trim(reference_version)) > 0', name='ck_cbs_reference_version_required'),
        sa.CheckConstraint('length(source_sha256) = 64', name='ck_cbs_source_hash_length'),
        sa.CheckConstraint('parent_code IS NULL OR parent_code <> cbs_code', name='ck_cbs_no_self_parent'),
    )
    op.create_table(
        'global_product_cbs_classifications',
        sa.Column('global_product_id', sa.Text(), sa.ForeignKey('global_products.id'), primary_key=True),
        sa.Column('cbs_code', sa.String(6), nullable=False),
        sa.Column('reference_version', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('confirmed_by', sa.Text(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('confirmation_source', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ['cbs_code', 'reference_version'],
            ['cbs_ecoicop_categories.cbs_code', 'cbs_ecoicop_categories.reference_version'],
            name='fk_product_cbs_reference',
        ),
        sa.CheckConstraint('version > 0', name='ck_product_cbs_version_positive'),
        sa.CheckConstraint('length(trim(confirmed_by)) > 0', name='ck_product_cbs_actor_required'),
    )
    op.create_index(
        'idx_global_product_cbs_category',
        'global_product_cbs_classifications',
        ['reference_version', 'cbs_code'],
    )
    op.create_table(
        'global_product_cbs_history',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('global_product_id', sa.Text(), nullable=False),
        sa.Column('cbs_code', sa.String(6), nullable=True),
        sa.Column('reference_version', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('confirmed_by', sa.Text(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('confirmation_source', sa.Text(), nullable=False),
        sa.CheckConstraint("action IN ('confirmed', 'removed')", name='ck_cbs_history_action'),
        sa.CheckConstraint('version > 0', name='ck_cbs_history_version_positive'),
        sa.CheckConstraint("(cbs_code IS NOT NULL AND action = 'confirmed') OR (cbs_code IS NULL AND action = 'removed')", name='ck_cbs_history_action_code'),
    )
    op.create_index('idx_cbs_history_product', 'global_product_cbs_history', ['global_product_id', 'confirmed_at'])
    for table in ('cbs_ecoicop_categories', 'global_product_cbs_classifications', 'global_product_cbs_history'):
        _guard(table)


def downgrade() -> None:
    bind = op.get_bind()
    for table in ('global_product_cbs_history', 'global_product_cbs_classifications', 'cbs_ecoicop_categories'):
        if bind.execute(sa.text(f'SELECT 1 FROM {table} LIMIT 1')).first():
            raise RuntimeError('CBS-gegevens aanwezig; automatische downgrade veilig gestopt.')
    op.drop_index('idx_cbs_history_product', table_name='global_product_cbs_history')
    op.drop_table('global_product_cbs_history')
    op.drop_index('idx_global_product_cbs_category', table_name='global_product_cbs_classifications')
    op.drop_table('global_product_cbs_classifications')
    op.drop_table('cbs_ecoicop_categories')
" if op.get_bind().dialect.name == 'postgresql'
            else "cbs_code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'",
            name='ck_cbs_code_six_digits',
        ),
        sa.CheckConstraint('level BETWEEN 1 AND 5', name='ck_cbs_level_valid'),
        sa.CheckConstraint('length(trim(name_nl)) > 0', name='ck_cbs_name_required'),
        sa.CheckConstraint('length(trim(reference_version)) > 0', name='ck_cbs_reference_version_required'),
        sa.CheckConstraint('length(source_sha256) = 64', name='ck_cbs_source_hash_length'),
        sa.CheckConstraint('parent_code IS NULL OR parent_code <> cbs_code', name='ck_cbs_no_self_parent'),
    )
    op.create_table(
        'global_product_cbs_classifications',
        sa.Column('global_product_id', sa.Text(), sa.ForeignKey('global_products.id'), primary_key=True),
        sa.Column('cbs_code', sa.String(6), nullable=False),
        sa.Column('reference_version', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('confirmed_by', sa.Text(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('confirmation_source', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ['cbs_code', 'reference_version'],
            ['cbs_ecoicop_categories.cbs_code', 'cbs_ecoicop_categories.reference_version'],
            name='fk_product_cbs_reference',
        ),
        sa.CheckConstraint('version > 0', name='ck_product_cbs_version_positive'),
        sa.CheckConstraint('length(trim(confirmed_by)) > 0', name='ck_product_cbs_actor_required'),
    )
    op.create_index(
        'idx_global_product_cbs_category',
        'global_product_cbs_classifications',
        ['reference_version', 'cbs_code'],
    )
    op.create_table(
        'global_product_cbs_history',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('global_product_id', sa.Text(), nullable=False),
        sa.Column('cbs_code', sa.String(6), nullable=True),
        sa.Column('reference_version', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('confirmed_by', sa.Text(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('confirmation_source', sa.Text(), nullable=False),
        sa.CheckConstraint("action IN ('confirmed', 'removed')", name='ck_cbs_history_action'),
        sa.CheckConstraint('version > 0', name='ck_cbs_history_version_positive'),
        sa.CheckConstraint("(cbs_code IS NOT NULL AND action = 'confirmed') OR (cbs_code IS NULL AND action = 'removed')", name='ck_cbs_history_action_code'),
    )
    op.create_index('idx_cbs_history_product', 'global_product_cbs_history', ['global_product_id', 'confirmed_at'])
    for table in ('cbs_ecoicop_categories', 'global_product_cbs_classifications', 'global_product_cbs_history'):
        _guard(table)


def downgrade() -> None:
    bind = op.get_bind()
    for table in ('global_product_cbs_history', 'global_product_cbs_classifications', 'cbs_ecoicop_categories'):
        if bind.execute(sa.text(f'SELECT 1 FROM {table} LIMIT 1')).first():
            raise RuntimeError('CBS-gegevens aanwezig; automatische downgrade veilig gestopt.')
    op.drop_index('idx_cbs_history_product', table_name='global_product_cbs_history')
    op.drop_table('global_product_cbs_history')
    op.drop_index('idx_global_product_cbs_category', table_name='global_product_cbs_classifications')
    op.drop_table('global_product_cbs_classifications')
    op.drop_table('cbs_ecoicop_categories')
