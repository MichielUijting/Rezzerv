"""Server boundary proof: no database or external Jumbo access is needed."""
from copy import deepcopy

import pytest

from app.integrations.retailer_receipts import RetailerReceiptEnvelope
from app.services.jumbo_receipt_validation import validate_jumbo_receipt_for_import


GOOD_RECEIPT = {
    "transactionId": "TXN-20261013-TEST",
    "purchaseDateTime": "2026-10-13T12:30:00",
    "storeName": "Jumbo Test",
    "grandTotal": 7.12,
    "discountTotal": 1.00,
    "depositTotal": 0.25,
    "items": [
        {"description": "BANANEN", "quantity": 2, "unitPrice": 0.94, "lineTotal": 1.88, "lineType": "product"},
        {"description": "KOFFIE", "quantity": 1, "unitPrice": 5.99, "lineTotal": 5.99, "lineType": "product"},
        {"description": "Korting koffie", "quantity": 1, "unitPrice": -1.00, "lineTotal": -1.00, "lineType": "discount"},
        {"description": "STATIEGELD", "quantity": 1, "unitPrice": 0.25, "lineTotal": 0.25, "lineType": "deposit"},
    ],
}


def envelope(data=None):
    return RetailerReceiptEnvelope(
        provider="jumbo", external_receipt_id="TXN-20261013-TEST",
        receipt=deepcopy(data if data is not None else GOOD_RECEIPT),
    )


def test_jumbo_server_accepts_reconciled_synthetic_receipt():
    assert validate_jumbo_receipt_for_import(envelope()) is None


@pytest.mark.parametrize("original_id", [
    "onwkasnmbz-a6743c22-cbbd-11f1-909c-ac190a7f0000.json",
    "JUMBO:2026/10.19",
    "ABC?DEF=123&456",
])
def test_jumbo_server_accepts_exact_printable_provider_id(original_id):
    receipt = deepcopy(GOOD_RECEIPT)
    receipt["transactionId"] = original_id
    payload = RetailerReceiptEnvelope(
        provider="jumbo",
        external_receipt_id=original_id,
        receipt=receipt,
    )
    assert validate_jumbo_receipt_for_import(payload) is None
    assert payload.external_receipt_id == original_id
    assert payload.receipt["transactionId"] == original_id


@pytest.mark.parametrize("unsafe_id", [
    "ID WITH SPACE",
    "ID\\tWITH_TAB",
    "ID\\nWITH_NEWLINE",
    "IDénonascii",
    "X" * 101,
])
def test_jumbo_server_rejects_unsafe_ids_without_modifying_them(unsafe_id):
    receipt = deepcopy(GOOD_RECEIPT)
    receipt["transactionId"] = unsafe_id
    payload = RetailerReceiptEnvelope(
        provider="jumbo",
        external_receipt_id=unsafe_id,
        receipt=receipt,
    )
    with pytest.raises(ValueError, match="Ongeldig Jumbo-bonnummer"):
        validate_jumbo_receipt_for_import(payload)


def test_jumbo_server_rejects_mismatching_source_id():
    receipt = deepcopy(GOOD_RECEIPT)
    receipt["transactionId"] = "JUMBO:123.456"
    payload = RetailerReceiptEnvelope(
        provider="jumbo",
        external_receipt_id="JUMBO:123.457",
        receipt=receipt,
    )
    with pytest.raises(ValueError, match="komt niet overeen"):
        validate_jumbo_receipt_for_import(payload)



@pytest.mark.parametrize("mutation", [
    lambda r: r.update(grandTotal=7.20),
    lambda r: r.update(depositTotal=0),
    lambda r: r.update(discountTotal=0),
    lambda r: r.update(purchaseDateTime="wrong"),
    lambda r: r.update(transactionId="WRONG-ID"),
    lambda r: r.update(items=[]),
    lambda r: r["items"][0].update(lineTotal=2.88),
    lambda r: r["items"][0].update(quantity=2.5),
    lambda r: r["items"][0].update(lineType="unknown"),
    lambda r: r["items"][2].update(lineTotal=1),
    lambda r: r["items"][1].update(unitPrice=-5.99, lineTotal=-5.99),
])
def test_jumbo_server_rejects_tampered_receipts(mutation):
    receipt = deepcopy(GOOD_RECEIPT)
    mutation(receipt)
    with pytest.raises(ValueError):
        validate_jumbo_receipt_for_import(envelope(receipt))
