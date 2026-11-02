"""Add isolated CBS ECOICOPv2 classification authority, without importing unverified data.

This is additive: existing Shopify, GS1, catalog, retail and inventory rows
are not touched. Reference data and confirmed assignments are populated only
through later, explicitly reviewed authority operations.
"""
from alembic import op
import sqlalchemy as sa
import json
from pathlib import Path
from datetime import date

_REFERENCE = Path(__file__).resolve().parents[2] / 'app' / 'data' / 'cbs_ecoicop_v2_2026_reference.json'
_SOURCE_SHA = '6871458274be87aa0126eab1bf334365502438f5e976845df8e5c28cdf95858f'
_EXPECTED_LEVELS = {1: 15, 2: 59, 3: 134, 4: 224, 5: 8}


def _seed_official_reference() -> None:
    """Import only the already cross-checked official CBS authority, never guesses."""
    if not _REFERENCE.is_file():
        raise RuntimeError('Gecontroleerde CBS-referentie ontbreekt; migratie veilig gestopt.')
    source = json.loads(_REFERENCE.read_text(encoding='utf-8'))
    if source.get('reference_version') != 'CBS-ECOICOPv2-2026' or source.get('source_sha256') != _SOURCE_SHA:
        raise RuntimeError('Onjuiste CBS-bronversie of SHA-256.')
    rows = source.get('categories')
    if not isinstance(rows, list) or len(rows) != 440:
        raise RuntimeError('CBS-referentie heeft niet exact 440 categorieën.')
    counts = {level: 0 for level in _EXPECTED_LEVELS}
    seen = set()
    parents = set()
    for row in rows:
        code, name = row.get('cbs_code'), row.get('name_nl')
        level, parent = row.get('level'), row.get('parent_code')
        if (not isinstance(code, str) or len(code) != 6 or not code.isascii() or
            not code.isdecimal() or code in seen or not isinstance(name, str) or not name.strip()
            or type(level) is not int or level not in counts):
            raise RuntimeError('Ongeldige CBS-code, naam of classificatieniveau.')
        seen.add(code)
        counts[level] += 1
        if parent is not None:
            parents.add(parent)
    if counts != _EXPECTED_LEVELS or not parents.issubset(seen):
        raise RuntimeError('CBS-hiërarchie of niveauaantallen wijken af van officiële bron.')
    by_code = {row['cbs_code']: row for row in rows}
    for row in rows:
        parent = row['parent_code']
        if parent is None:
            if row['level'] != 1:
                raise RuntimeError('Niet-hoofdcategorie zonder ouder.')
        elif by_code[parent]['level'] + 1 != row['level']:
            raise RuntimeError('CBS-ouder en niveau zijn inconsistent.')
        if bool(row.get('lowest')) != (row['cbs_code'] not in parents):
            raise RuntimeError('CBS laagste-groep-markering inconsistent.')
    if sum(row['lowest'] for row in rows) != 314:
        raise RuntimeError('CBS aantal laagste categorieën wijkt af.')
    bind = op.get_bind()
    existing = bind.execute(sa.text('SELECT COUNT(*) FROM cbs_ecoicop_categories')).scalar_one()
    if existing:
        raise RuntimeError('CBS-referentie bevat al gegevens; migratie stopt zonder overschrijven.')
    entries = [
        dict(
            cbs_code=row['cbs_code'], reference_version=source['reference_version'],
            name_nl=row['name_nl'], parent_code=row['parent_code'],
            level=row['level'], valid_from=date(2026, 1, 1),
            source_url=source['source_url'], source_sha256=_SOURCE_SHA,
            scope_notes='CBS ECOICOPv2 2026, officiële Excelrij ' + str(row['source_excel_row']),
        ) for row in rows
    ]
    # The parent FK is deferrable in PostgreSQL. SQLite's FK checks are
    # deferred by default in the migration harness; source rows are parent-first.
    table = sa.table('cbs_ecoicop_categories',
        sa.column('cbs_code', sa.String), sa.column('reference_version', sa.Text),
        sa.column('name_nl', sa.Text), sa.column('parent_code', sa.String),
        sa.column('level', sa.SmallInteger), sa.column('valid_from', sa.Date),
        sa.column('source_url', sa.Text), sa.column('source_sha256', sa.String),
        sa.column('scope_notes', sa.Text))
    op.bulk_insert(table, entries)



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
        sa.CheckConstraint("length(cbs_code) = 6 AND (substr(cbs_code, 1, 1) BETWEEN '0' AND '9') AND (substr(cbs_code, 2, 1) BETWEEN '0' AND '9') AND (substr(cbs_code, 3, 1) BETWEEN '0' AND '9') AND (substr(cbs_code, 4, 1) BETWEEN '0' AND '9') AND (substr(cbs_code, 5, 1) BETWEEN '0' AND '9') AND (substr(cbs_code, 6, 1) BETWEEN '0' AND '9')", name='ck_cbs_code_six_digits'),
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
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
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
    _seed_official_reference()  # DML before PostgreSQL maintenance-write triggers
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
