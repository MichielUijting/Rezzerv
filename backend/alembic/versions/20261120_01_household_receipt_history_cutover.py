"""Household-scoped start of trusted historical receipt learning.

This table is deliberately empty after upgrade. No existing receipt, household
or inventory event is reclassified by installing this revision.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261120_01"
down_revision = "20261114_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["receipt", "inventory", "auth", "shared"]


def upgrade() -> None:
    op.create_table(
        "household_receipt_history_cutovers",
        sa.Column(
            "household_id", sa.String(), sa.ForeignKey("household_registry.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("first_current_purchase_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "first_current_purchase_date >= DATE '2000-01-01'",
            name="ck_receipt_history_cutover_date",
        ),
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        schema = bind.execute(sa.text("SELECT current_schema()")).scalar_one()
        q = bind.dialect.identifier_preparer.quote_identifier
        bind.exec_driver_sql(
            "CREATE TRIGGER inhuis_maintenance_write_gate "
            "BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE "
            f"ON {q(schema)}.{q('household_receipt_history_cutovers')} FOR EACH STATEMENT "
            f"EXECUTE FUNCTION {q(schema)}.inhuis_maintenance_write_barrier()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text(
        "SELECT COUNT(*) FROM household_receipt_history_cutovers"
    )).scalar_one()
    if count:
        raise RuntimeError(
            "Historische ontvangstgrenzen bestaan; downgrade zou gegevens verliezen."
        )
    op.drop_table("household_receipt_history_cutovers")
