"""Restore an absent retailer queue without altering existing data.

A real PostgreSQL database had Alembic head 20261104_01 yet lacked
retailer_import_queue. This forward-only migration restores only a wholly
absent table and fails closed if an existing table has an incomplete schema.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "20261111_01"
down_revision = "20261104_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["receipt", "auth", "shared"]

TABLE = "retailer_import_queue"
COLUMNS = {
    "id", "household_id", "provider", "external_receipt_id",
    "payload_sha256", "payload_ciphertext", "status", "attempt_count",
    "last_error_code", "raw_receipt_id", "maintenance_operation_id",
    "created_at", "updated_at", "finished_at",
}


def _validate(bind, schema):
    i = inspect(bind)
    if {c["name"] for c in i.get_columns(TABLE, schema=schema)} != COLUMNS:
        raise RuntimeError("retailer_import_queue has an incomplete column layout")
    if set(i.get_pk_constraint(TABLE, schema=schema)["constrained_columns"]) != {"id"}:
        raise RuntimeError("retailer_import_queue primary key differs")
    if not {"ck_retailer_queue_provider", "ck_retailer_queue_status",
            "ck_retailer_queue_attempts"} <= {
                c["name"] for c in i.get_check_constraints(TABLE, schema=schema)}:
        raise RuntimeError("retailer_import_queue check constraints are missing")
    if "uq_retailer_import_queue_observation" not in {
            c["name"] for c in i.get_unique_constraints(TABLE, schema=schema)}:
        raise RuntimeError("retailer_import_queue unique constraint is missing")
    if "ix_retailer_import_queue_pending" not in {
            c["name"] for c in i.get_indexes(TABLE, schema=schema)}:
        raise RuntimeError("retailer_import_queue pending index is missing")
    guard = bind.execute(text("""
        SELECT pg_get_triggerdef(t.oid)
        FROM pg_trigger t
        WHERE t.tgrelid = to_regclass(:relation)
          AND t.tgname = 'inhuis_maintenance_write_gate' AND NOT t.tgisinternal
    """), {"relation": f"{schema}.{TABLE}"}).scalar_one_or_none()
    if not guard or "inhuis_maintenance_write_barrier" not in guard:
        raise RuntimeError("retailer_import_queue maintenance write barrier missing")


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # targeted PostgreSQL-only repair
    schema = bind.execute(text("SELECT current_schema()")).scalar_one()
    if inspect(bind).has_table(TABLE, schema=schema):
        _validate(bind, schema)
        return  # never modify an existing queue
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("external_receipt_id", sa.String(240), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("payload_ciphertext", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(60)),
        sa.Column("raw_receipt_id", sa.Text()),
        sa.Column("maintenance_operation_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("provider IN ('lidl','jumbo')",
                           name="ck_retailer_queue_provider"),
        sa.CheckConstraint("status IN ('pending','processing','completed','review_required')",
                           name="ck_retailer_queue_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_retailer_queue_attempts"),
        sa.UniqueConstraint("household_id", "provider", "external_receipt_id",
                            "payload_sha256", name="uq_retailer_import_queue_observation"),
    )
    op.create_index("ix_retailer_import_queue_pending", TABLE, ["status", "created_at"])
    q = bind.dialect.identifier_preparer.quote_identifier
    bind.exec_driver_sql(
        "CREATE TRIGGER inhuis_maintenance_write_gate "
        "BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE "
        f"ON {q(schema)}.{q(TABLE)} FOR EACH STATEMENT "
        f"EXECUTE FUNCTION {q(schema)}.inhuis_maintenance_write_barrier()"
    )
    _validate(bind, schema)


def downgrade():
    raise RuntimeError("Refuse destructive downgrade of retailer receipt queue")
