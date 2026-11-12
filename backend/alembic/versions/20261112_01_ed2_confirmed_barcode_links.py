"""Add Catalogus resolution to already-trusted manually saved ED2 barcodes.

Existing saved barcode values are unchanged and remain authoritative evidence.
Adds nullable resolution metadata; no automatic rewrite of household/receipt data.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261112_01"
down_revision = "20261111_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["catalog", "receipt", "shared"]


def upgrade() -> None:
    op.add_column("ed2_manual_barcodes", sa.Column(
        "global_product_id", sa.Text(), nullable=True,
    ))
    op.add_column("ed2_manual_barcodes", sa.Column(
        "barcode_scope", sa.String(32), nullable=True,
    ))
    op.add_column("ed2_manual_barcodes", sa.Column(
        "confirmed_by", sa.Text(), nullable=True,
    ))
    op.add_column("ed2_manual_barcodes", sa.Column(
        "confirmed_at", sa.DateTime(), nullable=True,
    ))
    # Keep the existing maintenance barrier, PK, and proven barcode evidence.


def downgrade() -> None:
    if op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM ed2_manual_barcodes WHERE global_product_id IS NOT NULL"
    )).scalar_one():
        raise RuntimeError(
            "Catalogus-koppelingen op opgeslagen barcodes bestaan; "
            "veilig downgraden is niet mogelijk."
        )
    for name in ("confirmed_at", "confirmed_by", "barcode_scope", "global_product_id"):
        op.drop_column("ed2_manual_barcodes", name)
