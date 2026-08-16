from decimal import Decimal

from app.integrations.receipt_scanners.adapters.rezzerv_legacy import RezzervLegacyScannerAdapter
from app.integrations.receipt_scanners.normalizer import canonical_to_receipt_parse_result
from app.integrations.receipt_scanners.schemas.scan_request_v1 import ScanRequestV1
from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics
from app.receipt_ingestion.service_parts.receipt_result_helpers import ReceiptParseResult
from app.services.receipt_ssot_status import apply_po_norm_status


def test_approved_summary_payload_does_not_reintroduce_line_sum_rejection():
    """Kassa list/detail summaries must honor the persisted scanner decision.

    The payload deliberately contains no line collection, as the production
    summary endpoints do. The numbers deliberately do not add up. This is a
    generic scanner-approval contract and contains no retailer-specific rule.
    """
    payload = {
        "store_name": "STORE-X",
        "total_amount": "104.95",
        "line_count": 33,
        "line_total_sum": "111.91",
        "net_line_total_sum": "116.44",
        "parse_status": "approved",
    }

    result = apply_po_norm_status(payload)

    assert result["po_norm_status_label"] == "Gecontroleerd"
    assert result["po_norm_failed_criteria"] == []
    assert "LINE_SUM_TOTAL_MISMATCH" not in result["po_norm_failed_criteria"]
    assert "parse_status" not in result


def test_nonapproved_summary_payload_still_fails_closed_on_line_sum_mismatch():
    payload = {
        "store_name": "STORE-X",
        "total_amount": "104.95",
        "line_count": 33,
        "line_total_sum": "111.91",
        "net_line_total_sum": "116.44",
        "parse_status": "review_needed",
    }

    result = apply_po_norm_status(payload)

    assert result["po_norm_status_label"] == "Controle nodig"
    assert "LINE_SUM_TOTAL_MISMATCH" in result["po_norm_failed_criteria"]


def test_structured_legacy_savings_role_becomes_loyalty_and_is_not_inventory_eligible():
    legacy = ReceiptParseResult(
        is_receipt=True,
        parse_status="approved",
        confidence_score=0.95,
        store_name="STORE-X",
        store_branch=None,
        purchase_at="2026-03-20T16:27:00",
        total_amount=Decimal("5.02"),
        discount_total=Decimal("0.00"),
        currency="EUR",
        lines=[
            {
                "line_type": "product",
                "raw_label": "OPAQUE-PRODUCT",
                "normalized_label": "OPAQUE-PRODUCT",
                "quantity": 1.0,
                "unit": None,
                "unit_price": 4.22,
                "line_total": 4.22,
                "discount_amount": 0.0,
                "barcode": None,
                "confidence_score": 0.95,
            },
            {
                "line_type": "spaarzegels",
                "is_spaarzegels": True,
                "exclude_from_inventory": True,
                "external_matching_allowed": False,
                "raw_label": "OPAQUE-SAVINGS-COMPONENT",
                "normalized_label": "OPAQUE-SAVINGS-COMPONENT",
                "quantity": 8.0,
                "unit": None,
                "unit_price": 0.10,
                "line_total": 0.80,
                "discount_amount": 0.0,
                "barcode": None,
                "confidence_score": 0.95,
            },
        ],
        parser_diagnostics={"contract": "structured-role-only"},
    )
    request = ScanRequestV1.from_bytes(
        scan_id="rscan_pr245_loyalty_contract",
        file_bytes=b"receipt bytes",
        filename="receipt.pdf",
        mime_type="application/pdf",
    )

    submission = RezzervLegacyScannerAdapter(parser=lambda *_args: legacy).submit(request)
    assert submission.result is not None
    assert submission.result.receipt is not None
    assert [line.line_type for line in submission.result.receipt.lines] == ["product", "loyalty"]

    normalized = canonical_to_receipt_parse_result(submission.result)
    assert [line["line_type"] for line in normalized.lines] == ["product", "loyalty"]

    product_semantics = derive_receipt_line_semantics(normalized.lines[0])
    loyalty_semantics = derive_receipt_line_semantics(normalized.lines[1])
    assert product_semantics == {"line_role": "product", "inventory_eligible": True}
    assert loyalty_semantics == {"line_role": "loyalty", "inventory_eligible": False}
