"""TD-05: durable server maintenance authority; additive, no user-data backfill."""
from alembic import op
import sqlalchemy as sa

revision = "20261021_01"
down_revision = "20261011_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["shared"]


def upgrade():
    op.create_table(
        "maintenance_control",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("announcement", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_json", sa.Text()),
        sa.Column("locked_boot_id", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("id=1", name="ck_maintenance_control_singleton"),
        sa.CheckConstraint("generation>=0", name="ck_maintenance_generation_nonnegative"),
        sa.CheckConstraint("state IN ('normal','announced','draining','locked','verifying','blocked')", name="ck_maintenance_valid_state"),
    )
    op.create_table(
        "maintenance_operations",
        sa.Column("operation_id", sa.String(36), primary_key=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("generation>=0", name="ck_maintenance_operation_generation"),
        sa.CheckConstraint("finished_at IS NULL OR finished_at>=started_at", name="ck_maintenance_operation_dates"),
    )
    op.create_index("ix_maintenance_operations_unfinished", "maintenance_operations", ["started_at"], postgresql_where=sa.text("finished_at IS NULL"))
    op.create_table(
        "maintenance_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Text(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.execute("INSERT INTO maintenance_control(id,state,generation) VALUES(1,'normal',0)")


def downgrade():
    # Never silently discard an active drain or unresolved crash evidence.
    conn=op.get_bind()
    state=conn.execute(sa.text("SELECT state FROM maintenance_control WHERE id=1")).scalar_one()
    active=conn.execute(sa.text("SELECT count(*) FROM maintenance_operations WHERE finished_at IS NULL")).scalar_one()
    if state != "normal" or active:
        raise RuntimeError("Beëindig onderhoud en reconcilieer verwerkingen vóór downgrade")
    op.drop_table("maintenance_audit")
    op.drop_index("ix_maintenance_operations_unfinished", table_name="maintenance_operations")
    op.drop_table("maintenance_operations")
    op.drop_table("maintenance_control")
