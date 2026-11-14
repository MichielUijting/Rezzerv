"""Exact user-confirmed ED2 receipt identities without invented GTINs.

Only the canonical retailer + receipt text + retailer article number tuple is
stored.  Synonyms, classification and operational inventory remain separate.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261113_01"
down_revision = "20261112_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["catalog", "receipt", "auth", "shared"]


def upgrade() -> None:
    op.create_table(
        "ed2_receipt_family_links",
        sa.Column("retailer_code", sa.Text(), primary_key=True),
        sa.Column("receipt_text_normalized", sa.Text(), primary_key=True),
        sa.Column("external_article_code", sa.Text(), primary_key=True),
        sa.Column("global_product_id", sa.Text(),
                  sa.ForeignKey("global_products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("match_mode", sa.Text(), nullable=False),
        sa.Column("confirmed_by", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("match_mode IN ('same_product', 'synonym_variant')",
                           name="ck_ed2_receipt_family_mode"),
    )
    op.create_index("idx_ed2_receipt_family_product",
                    "ed2_receipt_family_links", ["global_product_id"])
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        schema = conn.execute(sa.text("SELECT current_schema()")).scalar_one()
        quoted = conn.dialect.identifier_preparer.quote_identifier(schema)
        conn.exec_driver_sql(
            "CREATE TRIGGER inhuis_maintenance_write_gate "
            "BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE "
            f"ON {quoted}.ed2_receipt_family_links FOR EACH STATEMENT "
            f"EXECUTE FUNCTION {quoted}.inhuis_maintenance_write_barrier()"
        )


def downgrade() -> None:
    if op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM ed2_receipt_family_links"
    )).scalar_one():
        raise RuntimeError("Bevestigde bonartikelidentiteiten bestaan; veilig downgraden is niet mogelijk.")
    op.drop_index("idx_ed2_receipt_family_product", table_name="ed2_receipt_family_links")
    op.drop_table("ed2_receipt_family_links")
