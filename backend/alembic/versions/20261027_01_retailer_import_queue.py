"""Durable, household-scoped encrypted staging for confirmed retailer receipts.

Revision ID: 20261027_01
Revises: 20261026_01
"""
from alembic import op
import sqlalchemy as sa


revision = "20261027_01"
down_revision = "20261026_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["receipt", "auth"]


def upgrade() -> None:
    op.create_table(
        "retailer_import_queue",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("external_receipt_id", sa.String(240), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("payload_ciphertext", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(60), nullable=True),
        sa.Column("raw_receipt_id", sa.Text(), nullable=True),
        sa.Column("maintenance_operation_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("provider IN ('lidl','jumbo')", name="ck_retailer_queue_provider"),
        sa.CheckConstraint(
            "status IN ('pending','processing','completed','review_required')",
            name="ck_retailer_queue_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_retailer_queue_attempts"),
        sa.UniqueConstraint(
            "household_id", "provider", "external_receipt_id", "payload_sha256",
            name="uq_retailer_import_queue_observation",
        ),
    )
    op.create_index("ix_retailer_import_queue_pending", "retailer_import_queue",
                    ["status", "created_at"])
    # Maintenance v1 installs guards before this migration. New domain tables
    # must be enrolled explicitly; otherwise startup_preflight correctly fails.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        schema = bind.execute(sa.text("SELECT current_schema() ")).scalar_one()
        preparer = bind.dialect.identifier_preparer
        namespace = preparer.quote_identifier(schema)
        table = preparer.quote_identifier("retailer_import_queue")
        bind.exec_driver_sql(
            f"CREATE TRIGGER inhuis_maintenance_write_gate "
            f"BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON {namespace}.{table} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION {namespace}.inhuis_maintenance_write_barrier()"
        )


def downgrade() -> None:
    # No loss of staged receipt payloads even when they have completed. The
    # rollback first requires explicit archival/reconciliation and a new plan.
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT count(*) FROM retailer_import_queue")).scalar_one()
    if count:
        raise RuntimeError("Wachtrij bevat bongegevens; downgrade veilig geblokkeerd")
    op.drop_index("ix_retailer_import_queue_pending", table_name="retailer_import_queue")
    op.drop_table("retailer_import_queue")
