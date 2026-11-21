"""PR3 automatic, policy-owned historical opening-stock projection.

Revision ID: 20261121_01
Revises: 20261120_01

No legacy household is modified or backfilled at migration time.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261121_01"
down_revision = "20261120_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["receipt", "inventory", "auth", "shared"]


def upgrade() -> None:
    op.create_table(
        "household_historical_auto_stock_baselines",
        sa.Column("household_id", sa.Text(),
                  sa.ForeignKey("household_registry.id", ondelete="RESTRICT"),
                  primary_key=True),
        sa.Column("household_article_id", sa.Text(),
                  sa.ForeignKey("household_articles.id", ondelete="RESTRICT"),
                  primary_key=True),
        sa.Column("inventory_id", sa.Text(), nullable=True),
        sa.Column("inventory_event_id", sa.Text(), nullable=False, unique=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("first_current_purchase_date", sa.Date(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "quantity >= 0 AND quantity <= 1000000",
            name="ck_historical_auto_stock_quantity",
        ),
        sa.CheckConstraint(
            "(quantity = 0 AND inventory_id IS NULL) OR "
            "(quantity > 0 AND inventory_id IS NOT NULL)",
            name="ck_historical_auto_stock_projection",
        ),
    )
    op.create_index(
        "idx_historical_auto_stock_cutover",
        "household_historical_auto_stock_baselines",
        ["household_id", "first_current_purchase_date"],
    )
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        schema = conn.execute(sa.text("SELECT current_schema()")).scalar_one()
        quote = conn.dialect.identifier_preparer.quote_identifier
        conn.exec_driver_sql(
            "CREATE TRIGGER inhuis_maintenance_write_gate "
            "BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE "
            f"ON {quote(schema)}.{quote('household_historical_auto_stock_baselines')} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION {quote(schema)}.inhuis_maintenance_write_barrier()"
        )


def downgrade() -> None:
    conn = op.get_bind()
    count = conn.execute(sa.text(
        "SELECT COUNT(*) FROM household_historical_auto_stock_baselines"
    )).scalar_one()
    if count:
        raise RuntimeError(
            "Automatisch berekende historische beginvoorraad bestaat; downgrade mag geen data wissen."
        )
    op.drop_index(
        "idx_historical_auto_stock_cutover",
        table_name="household_historical_auto_stock_baselines",
    )
    op.drop_table("household_historical_auto_stock_baselines")
