"""Append-only, canonical classification synchronization audit for confirmed synonyms.

All events are written in the very transaction that applies the classification.
No household, receipt, or inventory records are created or modified.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261104_01'
down_revision = '20261102_01'
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ['catalog', 'auth', 'shared']


def upgrade():
    op.create_table(
        'article_classification_sync_events',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('event_key', sa.String(64), nullable=False, unique=True),
        sa.Column('source_product_id', sa.Text(), nullable=False),
        sa.Column('target_product_id', sa.Text(), nullable=False),
        sa.Column('classification_system', sa.String(3), nullable=False),
        sa.Column('classification_code', sa.Text(), nullable=False),
        sa.Column('reference_version', sa.Text(), nullable=False, server_default=''),
        sa.Column('decision_version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('actor_id', sa.Text(), nullable=False),
        sa.Column('related_event_id', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("classification_system IN ('GPC','CBS')", name='ck_article_sync_system'),
        sa.CheckConstraint(
            "status IN ('pending','processed','conflict','failed','review_required')",
            name='ck_article_sync_status'),
        sa.CheckConstraint('decision_version >= 0', name='ck_article_sync_version'),
        sa.CheckConstraint("source_product_id <> '' AND target_product_id <> ''",
                           name='ck_article_sync_ids'),
    )
    op.create_index('ix_article_sync_status_created', 'article_classification_sync_events',
                    ['status', 'created_at'])
    op.create_index('ix_article_sync_target', 'article_classification_sync_events',
                    ['target_product_id', 'classification_system'])
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        schema = bind.execute(sa.text('SELECT current_schema()')).scalar_one()
        quote = bind.dialect.identifier_preparer.quote_identifier
        bind.exec_driver_sql(
            'CREATE TRIGGER inhuis_maintenance_write_gate '
            'BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE '
            f'ON {quote(schema)}.{quote("article_classification_sync_events")} FOR EACH STATEMENT '
            f'EXECUTE FUNCTION {quote(schema)}.inhuis_maintenance_write_barrier()'
        )


def downgrade():
    if op.get_bind().execute(sa.text(
        'SELECT 1 FROM article_classification_sync_events LIMIT 1'
    )).first():
        raise RuntimeError('Synchronisatie-audit bevat historie; downgrade veilig gestopt.')
    op.drop_index('ix_article_sync_target', table_name='article_classification_sync_events')
    op.drop_index('ix_article_sync_status_created', table_name='article_classification_sync_events')
    op.drop_table('article_classification_sync_events')
