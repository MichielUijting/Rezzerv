"""Explicit user-confirmed ED2 barcode identities, scoped to one receipt identity.

Never promote historical ed2_manual_barcodes evidence automatically. Existing
receipts, Catalogus products, household articles, and stock are untouched.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261112_01"
down_revision = "20261031_02"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["catalog", "receipt", "shared"]


def upgrade() -> None:
    op.create_table(
        "ed2_confirmed_barcode_links",
        sa.Column("retailer_code", sa.String(128), nullable=False),
        sa.Column("receipt_text_normalized", sa.Text(), nullable=False),
        sa.Column("external_article_code", sa.String(256), nullable=False),
        sa.Column("barcode_value", sa.String(14), nullable=False),
        sa.Column("barcode_scope", sa.String(32), nullable=False),
        sa.Column("global_product_id", sa.Text(), nullable=False),
        sa.Column("confirmed_by", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint(
            "retailer_code", "receipt_text_normalized", "external_article_code",
            name="pk_ed2_confirmed_barcode_links",
        ),
        sa.CheckConstraint(
            "barcode_scope IN ('global_candidate', 'restricted')",
            name="ck_ed2_confirmed_barcode_links_scope",
        ),
        sa.ForeignKeyConstraint(["global_product_id"], ["global_products.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_ed2_confirmed_barcode_links_barcode",
        "ed2_confirmed_barcode_links", ["retailer_code", "barcode_value"],
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    bind = op.get_bind()
    schema = bind.execute(sa.text("SELECT current_schema()")).scalar_one()
    quoted = bind.dialect.identifier_preparer.quote_identifier
    bind.exec_driver_sql(
        "CREATE TRIGGER inhuis_maintenance_write_gate "
        "BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE "
        f"ON {quoted(schema)}.{quoted('ed2_confirmed_barcode_links')} "
        "FOR EACH STATEMENT "
        f"EXECUTE FUNCTION {quoted(schema)}.inhuis_maintenance_write_barrier()"
    )


def downgrade() -> None:
    rows = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM ed2_confirmed_barcode_links"
    )).scalar_one()
    if rows:
        raise RuntimeError(
            "Bevestigde barcodekoppelingen bestaan: veilig downgraden is niet mogelijk."
        )
    op.drop_index(
        "ix_ed2_confirmed_barcode_links_barcode",
        table_name="ed2_confirmed_barcode_links",
    )
    op.drop_table("ed2_confirmed_barcode_links")
