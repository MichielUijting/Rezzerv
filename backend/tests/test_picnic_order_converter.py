"""Account-free Picnic order fixture into Inhuis existing canonical Kassa boundary.

These are synthetic contract examples, not verified live Picnic responses.
Never create database records or mark final Picnic invoices as authenticated.
"""
import hashlib

import pytest

from app.integrations.picnic_order_converter import picnic_order_to_envelope
from app.integrations.picnic_readonly_probe import PicnicReadOnlyContractError
from app.integrations.retailer_receipts import normalize_retailer_receipt
from app.integrations.receipt_scanners.normalizer import canonical_to_receipt_parse_result
from app.services.retailer_receipt_import_service import import_retailer_receipt


def sample():
    def article(product_id, label):
        return {"type": "ORDER_ARTICLE", "id": product_id, "name": label,
                "price": 125, "unit_quantity": "1 st"}
    return {
        "delivery_id": "synthetic-delivery-1",
        "status": "COMPLETED",
        "orders": [{
            "type": "ORDER",
            "id": "synthetic-order-1",
            "status": "COMPLETED",
            "cancellation_time": None,
            "creation_time": "2026-10-12T11:00:00Z",
            "total_price": 475,
            "checkout_total_price": 475,
            "total_savings": 25,
            "total_deposit": 0,
            "fees": [],
            "items": [
                {"type": "ORDER_LINE", "id": "l1",
                 "items": [article("bread", "Brood"), article("bread", "Brood")],
                 "price": 250, "display_price": 250},
                {"type": "ORDER_LINE", "id": "l2",
                 "items": [article("milk", "Melk")],
                 "price": 250, "display_price": 225},
            ],
        }],
    }


def envelope():
    return picnic_order_to_envelope(sample(), "synthetic-order-1")


def test_synthetic_order_enters_existing_kassa_normalizer():
    result = envelope()
    assert result.provider == "picnic"
    assert result.external_receipt_id == "synthetic-delivery-1:synthetic-order-1"
    assert result.receipt["_picnic_invoice_verified"] is False
    canonical = normalize_retailer_receipt(
        result, scan_id="picnic_contract_test", document_sha256="f" * 64
    )
    assert canonical.receipt.store.name == "Picnic"
    assert canonical.receipt.transaction.receipt_number == result.external_receipt_id
    assert str(canonical.receipt.totals.grand_total) == "4.75"
    assert str(canonical.receipt.totals.discount_total) == "0.25"
    assert str(canonical.receipt.totals.deposit_total) == "0.00"
    assert len(canonical.receipt.lines) == 2
    assert str(canonical.receipt.lines[0].quantity) == "2"
    assert str(canonical.receipt.lines[0].unit_price) == "1.25"
    assert str(canonical.receipt.lines[0].line_total) == "2.50"
    assert str(canonical.receipt.lines[1].discount_amount) == "0.25"
    assert str(canonical.receipt.lines[1].line_total) == "2.25"
    parsed = canonical_to_receipt_parse_result(canonical)
    assert parsed.store_name == "Picnic"
    assert parsed.total_amount == canonical.receipt.totals.grand_total
    assert len(parsed.lines) == 2


def test_duplicate_order_observation_has_stable_identity_and_payload():
    first = envelope()
    second = envelope()
    assert first.external_receipt_id == second.external_receipt_id
    assert hashlib.sha256(first.stable_json_bytes()).hexdigest() == hashlib.sha256(second.stable_json_bytes()).hexdigest()


@pytest.mark.parametrize("change,expected", [
    ({"status": "CANCELLED"}, "Delivery not completed"),
    ({"orders": []}, "missing or ambiguous"),
])
def test_nonfinal_delivery_rejected(change, expected):
    data = sample()
    data.update(change)
    with pytest.raises(PicnicReadOnlyContractError, match=expected):
        picnic_order_to_envelope(data, "synthetic-order-1")


def test_ungrounded_deposit_cannot_be_added_to_stock():
    data = sample()
    data["orders"][0]["total_deposit"] = 25
    with pytest.raises(PicnicReadOnlyContractError, match="deposits require"):
        picnic_order_to_envelope(data, "synthetic-order-1")


def test_unknown_delivery_fee_requires_invoice_reconciliation():
    data = sample()
    data["orders"][0]["fees"] = [{"type": "DELIVERY", "value": 150}]
    with pytest.raises(PicnicReadOnlyContractError, match="financial adjustments"):
        picnic_order_to_envelope(data, "synthetic-order-1")


def test_missing_discount_not_silently_ignored():
    data = sample()
    data["orders"][0]["total_savings"] = 0
    with pytest.raises(PicnicReadOnlyContractError, match="savings do not reconcile"):
        picnic_order_to_envelope(data, "synthetic-order-1")


def test_missing_total_or_substitution_does_not_become_fake_inventory():
    data = sample()
    data["orders"][0]["items"][0]["items"][1]["id"] = "other"
    with pytest.raises(PicnicReadOnlyContractError, match="Mixed Picnic bundle"):
        picnic_order_to_envelope(data, "synthetic-order-1")


def test_picnic_import_disabled_even_if_envelope_is_structurally_valid():
    # Fail before any database or file access; no synthetic orders in live Kassa.
    with pytest.raises(ValueError, match="factuurvalidatie"):
        import_retailer_receipt(
            None, None, household_id="synthetic-household", envelope=envelope()
        )


def test_import_blocks_even_forged_invoice_verification_flag():
    supplied = envelope()
    supplied.receipt["_picnic_invoice_verified"] = True
    with pytest.raises(ValueError, match="factuurvalidatie"):
        import_retailer_receipt(None, None, household_id="synthetic-household", envelope=supplied)
