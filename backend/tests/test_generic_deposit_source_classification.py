"""Source-boundary deposit regression shared by OCR/text and retailer receipts."""
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics
from app.receipt_ingestion.service_parts.receipt_result_helpers import ReceiptParseResult
from app.services.receipt_service import parse_receipt_content


@pytest.mark.parametrize("label", [
    "6pak Ger. statiegeld", "Statiegeld 0,60", "EMBALLAGE",
    "Fust retour",
])
def test_legacy_parser_deposit_is_financial_not_inventory(label):
    original = ReceiptParseResult(
        is_receipt=True, parse_status="approved", confidence_score=0.99,
        store_name="Winkel", purchase_at="2026-10-11",
        total_amount=Decimal("4.00"), discount_total=None, currency="EUR",
        lines=[
            {"raw_label": label, "normalized_label": label, "line_total": 0.60},
            {"raw_label": "Melk", "normalized_label": "Melk", "line_total": 3.40},
        ],
    )
    with patch("app.services.receipt_service._parse_receipt_content_without_financial_typing", return_value=original):
        result = parse_receipt_content(b"receipt", "bon.txt", "text/plain")
    assert result.total_amount == Decimal("4.00")
    assert result.lines[0]["line_type"] == "deposit"
    assert derive_receipt_line_semantics(result.lines[0])["inventory_eligible"] is False
    assert derive_receipt_line_semantics(result.lines[1])["inventory_eligible"] is False  # Untyped fails closed


def test_legacy_explicit_financial_type_cannot_be_reclassified():
    original = ReceiptParseResult(
        is_receipt=True, parse_status="approved", confidence_score=0.99,
        store_name="Winkel", purchase_at="2026-10-11",
        total_amount=Decimal("0.60"), discount_total=None, currency="EUR",
        lines=[{"raw_label": "Statiegeld", "line_type": "payment", "line_total": 0.60}],
    )
    with patch("app.services.receipt_service._parse_receipt_content_without_financial_typing", return_value=original):
        result = parse_receipt_content(b"receipt", "bon.txt", "text/plain")
    assert result.lines[0]["line_type"] == "payment"


def test_unpriced_explanatory_deposit_line_not_promoted():
    original = ReceiptParseResult(
        is_receipt=True, parse_status="review_needed", confidence_score=0.7,
        store_name="Winkel", purchase_at="2026-10-11",
        total_amount=Decimal("1.00"), discount_total=None, currency="EUR",
        lines=[{"raw_label": "Statiegeld informatie", "normalized_label": "Statiegeld informatie"}],
    )
    with patch("app.services.receipt_service._parse_receipt_content_without_financial_typing", return_value=original):
        result = parse_receipt_content(b"receipt", "bon.txt", "text/plain")
    assert "line_type" not in result.lines[0]
