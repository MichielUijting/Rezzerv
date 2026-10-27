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
    else:
        # The historical SQLite baseline has an *unnamed* status check, while
        # PostgreSQL has the named constraint. SQLite batch reflection drops
        # unnamed CHECKs; explicitly carry forward every OTHER unnamed CHECK
        # (especially the required non-empty store-article identity check).
        current_checks = sa.inspect(conn).get_check_constraints(_TABLE)
        named_status = False
        preserved_anonymous_checks = []
        for check in current_checks:
            sql = str(check.get('sqltext') or '')
            name = check.get('name')
            is_status = name == _CHECK or (
                'status' in sql.lower() and "'confirmed'" in sql.lower()
            )
            if is_status:
                named_status = named_status or name == _CHECK
            elif not name:
                preserved_anonymous_checks.append(sa.CheckConstraint(sql))
        with op.batch_alter_table(
            _TABLE, recreate='always',
            table_args=tuple(preserved_anonymous_checks),
        ) as batch:
            if named_status:
                batch.drop_constraint(_CHECK, type_='check')
            batch.create_check_constraint(_CHECK, expression)


def upgrade() -> None:
    _replace_status_check("status IN ('confirmed', 'inactive', 'classification_pending')")


def downgrade() -> None:
    conn = op.get_bind()
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
