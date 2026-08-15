from decimal import Decimal

from sqlalchemy import create_engine, text

from app.integrations.receipt_scanners.adapters.rezzerv_legacy import RezzervLegacyScannerAdapter
from app.integrations.receipt_scanners.normalizer import canonical_to_receipt_parse_result
from app.integrations.receipt_scanners.schemas.canonical_receipt_v1 import CanonicalReceiptV1
from app.integrations.receipt_scanners.schemas.scan_request_v1 import ScanRequestV1
from app.integrations.receipt_scanners.validator import validate_canonical_receipt
from app.receipt_ingestion.service_parts.receipt_result_helpers import ReceiptParseResult


def _request() -> ScanRequestV1:
    return ScanRequestV1.from_bytes(
        scan_id="rscan_persistence_compat",
        file_bytes=b"receipt bytes",
        filename="receipt.jpg",
        mime_type="image/jpeg",
    )


def _assert_sqlite_persistable(line):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE receipt_line (quantity REAL, unit_price REAL, line_total REAL, discount_amount REAL)"
        ))
        conn.execute(
            text(
                "INSERT INTO receipt_line (quantity, unit_price, line_total, discount_amount) "
                "VALUES (:quantity, :unit_price, :line_total, :discount_amount)"
            ),
            {
                "quantity": line["quantity"],
                "unit_price": line["unit_price"],
                "line_total": line["line_total"],
                "discount_amount": line["discount_amount"],
            },
        )
        return conn.execute(text(
            "SELECT quantity, unit_price, line_total, discount_amount FROM receipt_line"
        )).mappings().one()


def test_legacy_provider_restores_numeric_contract_adds_role_and_persists():
    legacy = ReceiptParseResult(
        is_receipt=True,
        parse_status="approved",
        confidence_score=0.95,
        store_name="Store-X",
        store_branch="Branch-Y",
        purchase_at="2026-08-10",
        total_amount=Decimal("8.98"),
        discount_total=Decimal("0.00"),
        currency="EUR",
        lines=[{
            "raw_label": "ITEM-ALPHA 8,98",
            "normalized_label": "ITEM-ALPHA",
            "quantity": 2.0,
            "unit": "piece",
            "unit_price": 4.49,
            "line_total": 8.98,
            "discount_amount": 0.0,
            "barcode": None,
            "confidence_score": 0.95,
        }],
        parser_diagnostics={"fixture": "legacy"},
    )
    request = _request()
    submission = RezzervLegacyScannerAdapter(parser=lambda *_args: legacy).submit(request)
    canonical = validate_canonical_receipt(
        submission.result,
        expected_scan_id=request.scan_id,
        expected_sha256=request.document.sha256,
    )
    normalized = canonical_to_receipt_parse_result(canonical)
    line = normalized.lines[0]
    assert line["line_type"] == "product"
    assert {key: value for key, value in line.items() if key != "line_type"} == legacy.lines[0]
    assert all(isinstance(line[key], float) for key in (
        "quantity", "unit_price", "line_total", "discount_amount"
    ))
    persisted = _assert_sqlite_persistable(line)
    assert persisted["quantity"] == 2.0
    assert persisted["unit_price"] == 4.49
    assert persisted["line_total"] == 8.98
    assert persisted["discount_amount"] == 0.0


def test_external_provider_keeps_decimal_canonical_contract_but_normalizes_for_rezzerv_persistence():
    canonical = CanonicalReceiptV1(
        scan_id="rscan_external_persistence",
        provider={"code": "external-test", "job_id": "job-1", "result_id": "result-1"},
        status="completed",
        document={"sha256": "e" * 64, "mime_type": "image/jpeg", "page_count": 1},
        receipt={
            "store": {"name": "Store-X"},
            "transaction": {"purchase_date": "2026-08-10", "currency": "EUR"},
            "totals": {"grand_total": "8.98"},
            "lines": [{
                "line_number": 1,
                "line_type": "product",
                "raw_text": "ITEM-BETA 8,98",
                "description": "ITEM-BETA",
                "quantity": "2",
                "unit_price": "4.49",
                "line_total": "8.98",
                "discount_amount": "0.00",
            }],
            "warnings": [],
        },
        quality={"overall_confidence": 0.95, "requires_review": False},
    )
    canonical_line = canonical.receipt.lines[0]
    assert isinstance(canonical_line.quantity, Decimal)
    assert isinstance(canonical_line.unit_price, Decimal)
    assert isinstance(canonical_line.line_total, Decimal)

    normalized = canonical_to_receipt_parse_result(canonical)
    line = normalized.lines[0]
    assert line["line_type"] == "product"
    assert all(isinstance(line[key], float) for key in (
        "quantity", "unit_price", "line_total", "discount_amount"
    ))
    persisted = _assert_sqlite_persistable(line)
    assert persisted["unit_price"] == 4.49
    assert persisted["line_total"] == 8.98
