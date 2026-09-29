from __future__ import annotations

from decimal import Decimal

import pytest

from app.integrations.receipt_scanners.normalizer import canonical_to_receipt_parse_result
from app.integrations.retailer_receipts import RetailerReceiptEnvelope, normalize_retailer_receipt


@pytest.mark.parametrize(
    ("provider", "external_id", "receipt", "expected_store", "expected_barcode"),
    [
        (
            "ah",
            "ah-20260929-1",
            {
                "transactionId": "ah-20260929-1",
                "purchaseAt": "2026-09-29T18:30:00",
                "totalAmount": "5.48",
                "store": {"name": "AH testfiliaal", "city": "Arnhem"},
                "items": [
                    {"name": "Halfvolle melk", "quantity": 2, "unitPrice": "1.49", "totalPrice": "2.98", "ean": "8712345678906"},
                    {"name": "Brood", "quantity": 1, "unitPrice": "2.50", "totalPrice": "2.50"},
                ],
            },
            "Albert Heijn",
            "8712345678906",
        ),
        (
            "jumbo",
            "jumbo-20260929-1",
            {
                "receipt": {
                    "receiptNumber": "jumbo-20260929-1",
                    "transactionDateTime": "2026-09-29T17:15:00",
                    "grandTotal": "4.25",
                    "shop": {"name": "Jumbo testfiliaal"},
                    "products": [
                        {"description": "Yoghurt", "count": 1, "unitPrice": "1.75", "lineTotal": "1.75", "barcode": "8711111111116"},
                        {"description": "Fruit", "count": 2, "unitPrice": "1.25", "lineTotal": "2.50"},
                    ],
                }
            },
            "Jumbo",
            "8711111111116",
        ),
        (
            "lidl",
            "lidl-20260929-1",
            {
                "ticket": {
                    "id": "lidl-20260929-1",
                    "dateTime": "2026-09-29T16:45:00",
                    "total": "6.00",
                    "store": {"name": "Lidl testfiliaal"},
                    "basketItems": [
                        {"name": "Pasta", "quantity": 2, "currentUnitPrice": "1.50", "totalPrice": "3.00", "codeInput": "4056489000012"},
                        {"name": "Tomaten", "quantity": 1, "currentUnitPrice": "3.00", "totalPrice": "3.00"},
                    ],
                }
            },
            "Lidl",
            "4056489000012",
        ),
    ],
)
def test_structured_retailer_receipts_use_existing_canonical_contract(
    provider,
    external_id,
    receipt,
    expected_store,
    expected_barcode,
):
    envelope = RetailerReceiptEnvelope(
        provider=provider,
        external_receipt_id=external_id,
        receipt=receipt,
    )
    canonical = normalize_retailer_receipt(
        envelope,
        scan_id="rscan_test",
        document_sha256="a" * 64,
    )

    assert canonical.status == "completed"
    assert canonical.receipt is not None
    assert canonical.receipt.store.name == expected_store
    assert canonical.receipt.transaction.receipt_number == external_id
    assert canonical.receipt.totals.grand_total > Decimal("0")
    assert len(canonical.receipt.lines) == 2
    assert canonical.receipt.lines[0].identifiers is not None
    assert canonical.receipt.lines[0].identifiers.barcode == expected_barcode

    legacy = canonical_to_receipt_parse_result(canonical)
    assert legacy.is_receipt is True
    assert legacy.store_name == expected_store
    assert legacy.total_amount == canonical.receipt.totals.grand_total
    assert len(legacy.lines or []) == 2
    assert legacy.lines[0]["barcode"] == expected_barcode


def test_retailer_receipt_requires_lines():
    envelope = RetailerReceiptEnvelope(
        provider="ah",
        external_receipt_id="empty",
        receipt={"totalAmount": "1.00", "items": []},
    )
    with pytest.raises(ValueError, match="geen artikelregels"):
        normalize_retailer_receipt(
            envelope,
            scan_id="rscan_empty",
            document_sha256="b" * 64,
        )


def test_retailer_receipt_requires_total_or_line_totals():
    envelope = RetailerReceiptEnvelope(
        provider="jumbo",
        external_receipt_id="missing-total",
        receipt={"products": [{"description": "Onbekend artikel", "quantity": 1}]},
    )
    with pytest.raises(ValueError, match="totaalbedrag"):
        normalize_retailer_receipt(
            envelope,
            scan_id="rscan_missing_total",
            document_sha256="c" * 64,
        )
