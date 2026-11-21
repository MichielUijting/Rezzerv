"""PR3: immutable household opening-stock confirmations and idempotency.

Revision ID: 20261121_01
Revises: 20261120_01
No legacy stock/history data is migrated or initialized.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261121_01"
down_revision = "20261120_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["inventory", "receipt", "auth", "shared"]


def upgrade() -> None:
    op.create_table(
        "household_opening_stock_confirmations",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("household_id", sa.Text(),
                  sa.ForeignKey("household_registry.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("household_article_id", sa.Text(),
                  sa.ForeignKey("household_articles.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("proposal_key", sa.Text(), nullable=False),
        sa.Column("proposal_revision", sa.String(64), nullable=False),
        sa.Column("source_fingerprint", sa.Text(), nullable=False),
        sa.Column("first_current_purchase_date", sa.Date(), nullable=False),
        sa.Column("confirmed_quantity", sa.Integer(), nullable=False),
        sa.Column("confirmed_by_user_id", sa.Text(), nullable=False),
        sa.Column("inventory_id", sa.Text(), nullable=True),
        sa.Column("inventory_event_id", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("household_id", "household_article_id",
                            name="uq_household_opening_stock_confirmed_article"),
        sa.CheckConstraint(
            "confirmed_quantity >= 0 AND confirmed_quantity <= 10000",
            name="ck_household_opening_stock_confirmed_quantity",
        ),
        sa.CheckConstraint(
            "(confirmed_quantity = 0 AND inventory_id IS NULL AND inventory_event_id IS NULL)"
            " OR (confirmed_quantity > 0 AND inventory_id IS NOT NULL AND inventory_event_id IS NOT NULL)",
            name="ck_household_opening_stock_artifacts",
        ),
    )
    op.create_index(
        "idx_household_opening_stock_household",
        "household_opening_stock_confirmations", ["household_id", "confirmed_at"],
    )
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        schema = conn.execute(sa.text("SELECT current_schema()")).scalar_one()
        q = conn.dialect.identifier_preparer.quote_identifier
        conn.exec_driver_sql(
            "CREATE TRIGGER inhuis_maintenance_write_gate "
            "BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE "
            f"ON {q(schema)}.{q('household_opening_stock_confirmations')} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION {q(schema)}.inhuis_maintenance_write_barrier()"
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing = conn.execute(sa.text(
        "SELECT COUNT(*) FROM household_opening_stock_confirmations"
    )).scalar_one()
    if existing:
        raise RuntimeError("Bevestigde beginvoorraad bestaat; downgrade mag gegevens niet verliezen.")
    op.drop_index("idx_household_opening_stock_household",
                  table_name="household_opening_stock_confirmations")
    op.drop_table("household_opening_stock_confirmations")
