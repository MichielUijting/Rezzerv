"""Synthetic Jumbo phase 1 canonical Kassa contract.

No live Jumbo account, credentials, Docker or database are used.
"""
from decimal import Decimal

from app.integrations.retailer_receipts import RetailerReceiptEnvelope, normalize_retailer_receipt


def test_jumbo_products_discount_and_deposit_use_canonical_financial_types():
    envelope = RetailerReceiptEnvelope(
        provider="jumbo",
        external_receipt_id="TXN-20261013-TEST",
        receipt={
            "transactionId": "TXN-20261013-TEST",
            "purchaseDateTime": "2026-10-13T12:30:00",
            "storeName": "Jumbo Test",
            "grandTotal": 7.12,
            "discountTotal": 1.00,
            "depositTotal": 0.25,
            "items": [
                {"description": "BANANEN", "quantity": 2, "unitPrice": 0.94, "lineTotal": 1.88, "lineType": "product"},
                {"description": "KOFFIE", "quantity": 1, "unitPrice": 5.99, "lineTotal": 5.99, "lineType": "product"},
                {"description": "Korting koffie", "quantity": 1, "unitPrice": -1, "lineTotal": -1, "lineType": "discount"},
                {"description": "STATIEGELD", "quantity": 1, "unitPrice": 0.25, "lineTotal": 0.25, "lineType": "deposit"},
            ],
        },
    )
    result = normalize_retailer_receipt(envelope, scan_id="jumbo_phase1", document_sha256="e" * 64)
    assert result.receipt is not None
    assert result.receipt.store.name == "Jumbo"
    assert result.receipt.transaction.receipt_number == "TXN-20261013-TEST"
    assert result.receipt.totals.grand_total == Decimal("7.12")
    assert result.receipt.totals.discount_total == Decimal("1.0")
    assert result.receipt.totals.deposit_total == Decimal("0.25")
    assert [line.line_type for line in result.receipt.lines] == [
        "product", "product", "discount", "deposit",
    ]
    assert len([line for line in result.receipt.lines if line.line_type == "product"]) == 2
    assert result.receipt.lines[0].quantity == Decimal("2")
    assert result.receipt.lines[2].line_total == Decimal("-1")
