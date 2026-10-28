"""Allow verified Catalogus GTIN links to await official GS1 classification.

Receipt/inventory consumers continue to require complete official GPC evidence;
classification_pending is solely a staging status for Externe databases 2.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261027_02'
down_revision = '20261026_01'
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ['catalog', 'receipt', 'shared']

_TABLE = 'external_article_product_links'
_CHECK = 'ck_external_article_product_links_status'


def _replace_status_check(expression: str) -> None:
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.drop_constraint(_CHECK, _TABLE, type_='check')
        op.create_check_constraint(_CHECK, _TABLE, expression)
    # The SQLite source is an immutable historical migration baseline. Its
    # existing table definitions are verified byte-for-byte by CI and must
    # not be rewritten by an additive PostgreSQL operational feature.


def upgrade() -> None:
    _replace_status_check("status IN ('confirmed', 'inactive', 'classification_pending')")


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    count = conn.execute(sa.text(
        "SELECT COUNT(*) FROM external_article_product_links "
        "WHERE status = 'classification_pending'"
    )).scalar_one()
    if count:
        raise RuntimeError(
            'Veilig gestopt: classificatie-wachtende Cataloguskoppelingen bestaan. '
            'Downgrade zou hun betekenis verliezen; maak eerst een expliciet herstelplan.'
        )
    _replace_status_check("status IN ('confirmed', 'inactive')")
