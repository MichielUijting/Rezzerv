"""Picnic adapter -> canonical receipt -> inventory eligibility, then real PG chain.

The existing production chain is independently PostgreSQL backed; Picnic
Kassa writes remain forbidden until verified live invoices. This test does
not claim that a Picnic receipt passed Kassa-to-Unpacking persistence.
"""
from __future__ import annotations

from decimal import Decimal

from app.integrations.picnic_order_converter import picnic_order_to_envelope
from app.integrations.retailer_receipts import normalize_retailer_receipt
from app.integrations.receipt_scanners.normalizer import canonical_to_receipt_parse_result
from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics
from app.testing.postgresql_receipt_inventory_production_chain import run_production_chain
from app.services.retailer_receipt_import_service import import_retailer_receipt


def synthetic_picnic_delivery():
    def line(article_id, name, qty, unit_price_cents):
        return {
            "type": "ORDER_LINE",
            "id": f"line-{article_id}",
            "items": [
                {"type": "ORDER_ARTICLE", "id": article_id, "name": name}
                for _ in range(qty)
            ],
            "price": qty * unit_price_cents,
            "display_price": qty * unit_price_cents,
        }
    return {
        "delivery_id": "picnic-isolated-proof-delivery",
        "status": "COMPLETED",
        "orders": [{
            "type": "ORDER", "id": "picnic-isolated-proof-order",
            "status": "COMPLETED", "cancellation_time": None,
            "creation_time": "2026-10-13T14:30:00Z",
            "items": [
                line("synthetic-bread", "Picnic brood", 2, 125),
                line("synthetic-milk", "Picnic melk", 3, 100),
            ],
            "total_price": 575,
            "checkout_total_price": 575,
            "total_savings": 0,
            "total_deposit": 25,
            "deposit_breakdown": [{"type": "DEFAULT", "value": 25, "count": 1}],
            "fees": [],
        }],
    }


def run_picnic_postgresql_proof() -> None:
    envelope = picnic_order_to_envelope(
        synthetic_picnic_delivery(), "picnic-isolated-proof-order"
    )
    receipt = normalize_retailer_receipt(
        envelope, scan_id="picnic_isolated_pg_chain", document_sha256="a" * 64
    )
    assert receipt.receipt is not None
    assert receipt.receipt.store.name == "Picnic"
    assert receipt.receipt.totals.grand_total == Decimal("5.75")
    assert receipt.receipt.totals.deposit_total == Decimal("0.25")
    legacy = canonical_to_receipt_parse_result(receipt)
    assert legacy.parse_status == "review_needed"
    assert [x["quantity"] for x in legacy.lines[:2]] == [2.0, 3.0]
    assert [derive_receipt_line_semantics(x)["inventory_eligible"] for x in legacy.lines] == [True, True, False]
    assert sum(
        Decimal(str(x["quantity"])) for x in legacy.lines
        if derive_receipt_line_semantics(x)["inventory_eligible"]
    ) == Decimal("5")
    assert envelope.external_receipt_id == picnic_order_to_envelope(
        synthetic_picnic_delivery(), "picnic-isolated-proof-order"
    ).external_receipt_id
    print("PICNIC_SYNTHETIC_CANONICAL_INVENTORY_ELIGIBILITY_GREEN")

    # With a working, migrated, disposable PostgreSQL connection, even a
    # correctly shaped synthetic Picnic source must be rejected by Kassa.
    # Existing data should not change in response to an unverified invoice.
    from app.db import engine
    from sqlalchemy import text
    assert engine.dialect.name == "postgresql"
    with engine.connect() as conn:
        pre = conn.execute(text("SELECT count(*) FROM receipt_tables")).scalar_one()
    try:
        import_retailer_receipt(
            engine, None, household_id="0", envelope=envelope
        )
    except ValueError as exc:
        assert "factuurvalidatie" in str(exc)
    else:
        raise AssertionError("Unverified Picnic receipt unexpectedly imported")
    with engine.connect() as conn:
        post = conn.execute(text("SELECT count(*) FROM receipt_tables")).scalar_one()
    assert pre == post
    print("PICNIC_POSTGRESQL_UNVERIFIED_IMPORT_NO_WRITE_GREEN")

    # Reuse the established DML-only real PostgreSQL Kassa/inventory pipeline
    # and its idempotency checks. This still uses its existing AH test fixtures,
    # not a persisted Picnic source; the distinction is documented.
    result = run_production_chain()
    assert result["datastore"] == "postgresql"
    assert result["inventory_path"] == [0, 2, 5, 5, 1]
    assert result["purchase_event_path"] == [0, 1, 2, 2]
    assert result["migration_credential_available"] is False
    print("PICNIC_ADAPTER_PLUS_EXISTING_POSTGRESQL_CHAIN_GREEN")


if __name__ == "__main__":
    run_picnic_postgresql_proof()
