"""Track incomplete Jumbo history scans separately from receipt ingestion.

No existing data is rewritten. An unfinished range is never skipped because a
newer receipt was imported before an older batch finished.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261125_01"
down_revision = "20261123_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["receipt", "auth", "shared"]


def upgrade() -> None:
    op.create_table(
        "household_jumbo_import_runs",
        sa.Column("household_id", sa.Text(),
                  sa.ForeignKey("household_registry.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("pending_from_date", sa.Date(), nullable=False),
        sa.Column("scan_complete", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("queue_ids", sa.JSON(), nullable=False,
                  server_default=sa.text("'[]'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("pending_from_date >= '2000-01-01'",
                           name="ck_jumbo_history_start"),
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        schema = bind.execute(sa.text("SELECT current_schema()")).scalar_one()
        q = bind.dialect.identifier_preparer.quote_identifier
        bind.exec_driver_sql(
            "CREATE TRIGGER inhuis_maintenance_write_gate "
            "BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE "
            f"ON {q(schema)}.{q('household_jumbo_import_runs')} FOR EACH STATEMENT "
            f"EXECUTE FUNCTION {q(schema)}.inhuis_maintenance_write_barrier()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM household_jumbo_import_runs")).scalar_one():
        raise RuntimeError("Jumbo-herstelstatus bestaat; downgrade mag die niet wissen")
    op.drop_table("household_jumbo_import_runs")
