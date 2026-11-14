"""Global user-confirmed bonnaam aliases for safe exact receipt-name matching.

User-approved HV Melk -> Halfvolle melk applies across retailers and receipt
article numbers only while central evidence remains unique and consistent.
No product, household, stock or barcode data is modified by this migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261114_01"
down_revision = "20261113_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["catalog", "receipt", "auth", "shared"]


def upgrade() -> None:
    op.create_table(
        "ed2_receipt_name_aliases",
        sa.Column("alias_name_normalized", sa.Text(), primary_key=True),
        sa.Column("target_name_normalized", sa.Text(), nullable=False),
        sa.Column("global_product_id", sa.Text(),
                  sa.ForeignKey("global_products.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("confirmed_by", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("alias_name_normalized <> target_name_normalized",
                           name="ck_ed2_receipt_name_alias_distinct"),
    )
    op.create_index("idx_ed2_receipt_name_alias_product",
                    "ed2_receipt_name_aliases", ["global_product_id"])
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        schema = conn.execute(sa.text("SELECT current_schema()")).scalar_one()
        quoted = conn.dialect.identifier_preparer.quote_identifier(schema)
        conn.exec_driver_sql(
            "CREATE TRIGGER inhuis_maintenance_write_gate "
            "BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE "
            f"ON {quoted}.ed2_receipt_name_aliases FOR EACH STATEMENT "
            f"EXECUTE FUNCTION {quoted}.inhuis_maintenance_write_barrier()"
        )


def downgrade() -> None:
    if op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM ed2_receipt_name_aliases"
    )).scalar_one():
        raise RuntimeError("Bevestigde bonnaamrelaties bestaan; downgraden is niet veilig.")
    op.drop_index("idx_ed2_receipt_name_alias_product",
                  table_name="ed2_receipt_name_aliases")
    op.drop_table("ed2_receipt_name_aliases")
