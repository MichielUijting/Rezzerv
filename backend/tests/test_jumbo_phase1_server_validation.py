"""Server boundary proof: no database or external Jumbo access is needed."""
from copy import deepcopy

import pytest

from app.integrations.retailer_receipts import RetailerReceiptEnvelope
from app.services.retailer_receipt_import_service import validate_jumbo_receipt_for_import


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
