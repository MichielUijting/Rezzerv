from decimal import Decimal

from app.integrations.receipt_scanners.adapters.rezzerv_legacy import (
    RezzervLegacyScannerAdapter,
)
from app.integrations.receipt_scanners.normalizer import canonical_to_receipt_parse_result
from app.integrations.receipt_scanners.schemas.scan_request_v1 import ScanRequestV1
from app.integrations.receipt_scanners.validator import validate_canonical_receipt
from app.receipt_ingestion.service_parts.receipt_result_helpers import ReceiptParseResult


def _legacy_result(line_count: int = 17) -> ReceiptParseResult:
    lines = []
    for index in range(line_count):
        amount = Decimal('1.00')
        lines.append({
            'line_type': 'product',
            'raw_label': f'ITEM-{index + 1:02d}',
            'normalized_label': f'ITEM-{index + 1:02d}',
            'quantity': 1.0,
            'unit': None,
            'unit_price': float(amount),
            'line_total': float(amount),
            'discount_amount': None,
            'barcode': None,
            'confidence_score': 0.96,
        })
    return ReceiptParseResult(
        is_receipt=True,
        parse_status='approved',
        confidence_score=0.96,
        store_name='STORE-X',
        store_branch='BRANCH-X',
        purchase_at='2026-06-01T14:35:00',
        total_amount=Decimal(str(line_count)),
        discount_total=None,
        currency='EUR',
        lines=lines,
        parser_diagnostics={
            'total_candidates': line_count,
            'appended_candidates': line_count,
            'blocked_candidates': 0,
            'by_classification': {'continuation': line_count},
        },
    )


def test_legacy_scanner_boundary_preserves_all_17_parser_lines_and_order():
    legacy = _legacy_result(17)
    request = ScanRequestV1.from_bytes(
        scan_id='rscan_line_count_equivalence',
        file_bytes=b'opaque receipt bytes',
        filename='opaque-receipt.jpg',
        mime_type='image/jpeg',
    )

    submission = RezzervLegacyScannerAdapter(parser=lambda *_args: legacy).submit(request)
    canonical = validate_canonical_receipt(
        submission.result,
        expected_scan_id=request.scan_id,
        expected_sha256=request.document.sha256,
    )
    normalized = canonical_to_receipt_parse_result(canonical)

    assert len(canonical.receipt.lines) == 17
    assert len(normalized.lines) == 17
    assert [line['raw_label'] for line in normalized.lines] == [
        line['raw_label'] for line in legacy.lines
    ]
    assert [line['line_total'] for line in normalized.lines] == [
        line['line_total'] for line in legacy.lines
    ]
