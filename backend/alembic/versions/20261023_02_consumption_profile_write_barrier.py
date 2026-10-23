"""Protect derived profiles, including databases already at 20261023_01."""
from alembic import op
import sqlalchemy as sa

revision = '20261023_02'
down_revision = '20261023_01'
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ['shared']


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    schema = conn.execute(sa.text('SELECT current_schema()')).scalar_one()
    quoted = conn.dialect.identifier_preparer.quote_identifier(schema)
    # Reuse the existing maintenance authority; never exempt this domain table
    # from the fail-closed startup check or grant runtime schema privileges.
    conn.exec_driver_sql(
        'CREATE TRIGGER inhuis_maintenance_write_gate '
        'BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE '
        f'ON {quoted}.global_product_consumption_profiles '
        'FOR EACH STATEMENT EXECUTE FUNCTION '
        f'{quoted}.inhuis_maintenance_write_barrier()'
    )


def downgrade():
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    schema = conn.execute(sa.text('SELECT current_schema()')).scalar_one()
    quoted = conn.dialect.identifier_preparer.quote_identifier(schema)
    conn.exec_driver_sql(
        'DROP TRIGGER inhuis_maintenance_write_gate '
        f'ON {quoted}.global_product_consumption_profiles'
    )
