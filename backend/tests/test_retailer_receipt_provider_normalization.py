from __future__ import annotations

from decimal import Decimal

import json

import pytest

from app.integrations.receipt_scanners.adapters.retailer_structured import StructuredRetailerReceiptScannerAdapter
from app.integrations.receipt_scanners.gateway import ReceiptScannerGateway
from app.integrations.receipt_scanners.normalizer import canonical_to_receipt_parse_result
from app.integrations.receipt_scanners.registry import ProviderRegistry
from app.integrations.receipt_scanners.schemas.scan_request_v1 import ScanRequestV1
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


def test_structured_retailer_adapter_uses_receipt_scanner_gateway():
    envelope = RetailerReceiptEnvelope(
        provider="ah",
        external_receipt_id="gateway-test",
        receipt={
            "purchaseAt": "2026-09-29T19:00:00",
            "totalAmount": "2.49",
            "items": [
                {
                    "name": "Testartikel",
                    "quantity": 1,
                    "unitPrice": "2.49",
                    "totalPrice": "2.49",
                    "ean": "8712345678906",
                }
            ],
        },
    )
    raw = json.dumps(envelope.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    request = ScanRequestV1.from_bytes(
        scan_id="rscan_retailer_gateway",
        file_bytes=raw,
        filename="ah-gateway-test.inhuis-receipt.json",
        mime_type="application/vnd.inhuis.retailer-receipt+json",
    )
    provider = StructuredRetailerReceiptScannerAdapter()
    gateway = ReceiptScannerGateway(
        ProviderRegistry([provider], active_provider_code=provider.provider_code),
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    canonical = gateway.scan(request)
    normalized = canonical_to_receipt_parse_result(canonical)

    assert canonical.provider is not None
    assert canonical.provider.code == "retailer-ah"
    assert canonical.document is not None
    assert canonical.document.sha256 == request.document.sha256
    assert normalized.store_name == "Albert Heijn"
    assert normalized.lines[0]["barcode"] == "8712345678906"


def test_lidl_web_receipt_preserves_rich_product_semantics():
    envelope = RetailerReceiptEnvelope(
        provider="lidl",
        external_receipt_id="22000742902026090914942",
        receipt={
            "id": "22000742902026090914942",
            "dateTime": "2026-09-09T14:42:00",
            "totalAmount": "6.15",
            "discountTotal": "1.00",
            "depositTotal": "0.25",
            "paidTotal": "6.15",
            "products": [
                {
                    "name": "FRISDRANK 1,5L",
                    "quantity": "2",
                    "unit": "1.5 l",
                    "unitPrice": "2.50",
                    "grossAmount": "5.00",
                    "discountAmount": "1.00",
                    "lineTotal": "4.00",
                    "articleId": "123456",
                    "retailerSku": "123456",
                    "barcode": "4056489000012",
                    "codeInput": "4056489000012",
                    "taxRate": "21",
                    "discounts": [{"description": "Lidl Plus korting", "amount": "1.00"}],
                },
                {
                    "name": "Statiegeld",
                    "quantity": "1",
                    "unitPrice": "0.25",
                    "lineTotal": "0.25",
                    "lineType": "deposit",
                },
                {
                    "name": "BROOD",
                    "quantity": "1",
                    "unitPrice": "1.90",
                    "lineTotal": "1.90",
                    "articleId": "654321",
                    "retailerSku": "654321",
                    "taxRate": "9",
                },
            ],
        },
    )

    canonical = normalize_retailer_receipt(
        envelope,
        scan_id="rscan_lidl_web_rich",
        document_sha256="d" * 64,
    )
    assert canonical.receipt is not None
    assert canonical.receipt.totals.discount_total == Decimal("1.00")
    assert canonical.receipt.totals.deposit_total == Decimal("0.25")
    assert canonical.receipt.totals.paid_total == Decimal("6.15")

    first = canonical.receipt.lines[0]
    assert first.description == "FRISDRANK 1,5L"
    assert first.quantity == Decimal("2")
    assert first.unit == "1.5 l"
    assert first.unit_price == Decimal("2.50")
    assert first.gross_amount == Decimal("5.00")
    assert first.discount_amount == Decimal("1.00")
    assert first.line_total == Decimal("4.00")
    assert first.identifiers is not None
    assert first.identifiers.gtin == "4056489000012"
    assert first.identifiers.retailer_sku == "123456"
    assert first.tax is not None
    assert first.tax.rate == Decimal("21")

    legacy = canonical_to_receipt_parse_result(canonical)
    assert legacy.lines[0]["quantity"] == 2.0
    assert legacy.lines[0]["unit"] == "1.5 l"
    assert legacy.lines[0]["unit_price"] == 2.5
    assert legacy.lines[0]["discount_amount"] == 1.0
    assert legacy.lines[0]["line_total"] == 4.0
    assert legacy.lines[0]["barcode"] == "4056489000012"
    assert legacy.lines[0]["retailer_sku"] == "123456"

    assert canonical.receipt.lines[1].line_type == "deposit"
    assert canonical.receipt.lines[1].line_total == Decimal("0.25")


def test_lidl_weight_detail_row_is_metadata_not_second_purchase_component():
    envelope = RetailerReceiptEnvelope(
        provider="lidl",
        external_receipt_id="lidl-weight-detail",
        receipt={
            "totalAmount": "4.42",
            "products": [
                {
                    "name": "Gewogen artikel",
                    "quantity": "0.122",
                    "unitPrice": "19.90",
                    "grossAmount": "2.43",
                    "lineTotal": "2.43",
                    "articleId": "6612989",
                },
                {
                    "name": "Gewogen artikel",
                    "quantity": "0.122",
                    "unit": "0.122 kg",
                    "unitPrice": "19.90",
                    "grossAmount": None,
                    "lineTotal": None,
                    "packageSize": "0.122 kg",
                    "articleId": "6612989",
                },
                {
                    "name": "Ander artikel",
                    "quantity": "1",
                    "unitPrice": "1.99",
                    "grossAmount": "1.99",
                    "lineTotal": "1.99",
                    "articleId": "1234567",
                },
            ],
        },
    )

    canonical = normalize_retailer_receipt(
        envelope,
        scan_id="rscan_lidl_weight_detail",
        document_sha256="e" * 64,
    )

    assert canonical.receipt is not None
    assert len(canonical.receipt.lines) == 2
    weighted = canonical.receipt.lines[0]
    assert weighted.description == "Gewogen artikel"
    assert weighted.quantity == Decimal("0.122")
    assert weighted.unit_price == Decimal("19.90")
    assert weighted.line_total == Decimal("2.43")
    assert weighted.identifiers is not None
    assert weighted.identifiers.retailer_sku == "6612989"
    assert sum(
        line.line_total or Decimal("0")
        for line in canonical.receipt.lines
        if line.line_type in {"product", "deposit"}
    ) == Decimal("4.42")


def test_lidl_weight_detail_discount_is_applied_to_priced_article():
    envelope = RetailerReceiptEnvelope(
        provider="lidl",
        external_receipt_id="lidl-weight-discount",
        receipt={
            "totalAmount": "3.06",
            "discountTotal": "1.17",
            "products": [
                {
                    "name": "Gewogen artikel",
                    "quantity": "1.224",
                    "unitPrice": "2.65",
                    "grossAmount": "3.24",
                    "lineTotal": "3.24",
                    "articleId": "0080755",
                },
                {
                    "name": "Gewogen artikel",
                    "quantity": "1.224",
                    "unit": "1.224 kg",
                    "unitPrice": "2.65",
                    "grossAmount": None,
                    "lineTotal": "0.00",
                    "discountAmount": "1.17",
                    "packageSize": "1.224 kg",
                    "articleId": "0080755",
                },
                {
                    "name": "Ander artikel",
                    "quantity": "1",
                    "unitPrice": "0.99",
                    "grossAmount": "0.99",
                    "lineTotal": "0.99",
                    "articleId": "7654321",
                },
            ],
        },
    )

    canonical = normalize_retailer_receipt(
        envelope,
        scan_id="rscan_lidl_weight_discount",
        document_sha256="f" * 64,
    )

    assert canonical.receipt is not None
    assert len(canonical.receipt.lines) == 2
    weighted = canonical.receipt.lines[0]
    assert weighted.gross_amount == Decimal("3.24")
    assert weighted.discount_amount == Decimal("1.17")
    assert weighted.line_total == Decimal("2.07")
    assert canonical.receipt.totals.discount_total == Decimal("1.17")
    assert sum(
        line.line_total or Decimal("0")
        for line in canonical.receipt.lines
        if line.line_type in {"product", "deposit"}
    ) == Decimal("3.06")
