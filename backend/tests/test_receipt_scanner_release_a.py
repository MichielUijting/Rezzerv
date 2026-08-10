from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.integrations.receipt_scanners.adapters.fake_test_provider import FakeScannerProvider
from app.integrations.receipt_scanners.adapters.rezzerv_legacy import RezzervLegacyScannerAdapter
from app.integrations.receipt_scanners.errors import ProviderConfigurationError
from app.integrations.receipt_scanners.gateway import ReceiptScannerGateway
from app.integrations.receipt_scanners.normalizer import canonical_to_receipt_parse_result
from app.integrations.receipt_scanners.registry import ProviderRegistry
from app.integrations.receipt_scanners.runtime import reset_receipt_scanner_runtime_cache, validate_receipt_scanner_configuration
from app.integrations.receipt_scanners.schemas.canonical_receipt_v1 import CanonicalReceiptV1
from app.integrations.receipt_scanners.schemas.scan_request_v1 import ScanRequestV1
from app.integrations.receipt_scanners.validator import validate_canonical_receipt
from app.receipt_ingestion.service_parts.receipt_result_helpers import ReceiptParseResult


def _legacy_result() -> ReceiptParseResult:
    return ReceiptParseResult(
        is_receipt=True,
        parse_status="approved",
        confidence_score=0.91,
        store_name="Lidl",
        store_branch="Driel",
        purchase_at="2026-08-03",
        total_amount=Decimal("2.78"),
        discount_total=Decimal("0.00"),
        currency="EUR",
        lines=[{
            "raw_label": "2 MELK HALF VOL 1L 2,78",
            "normalized_label": "Melk halfvol 1L",
            "quantity": 2.0,
            "unit": "piece",
            "unit_price": 1.39,
            "line_total": 2.78,
            "discount_amount": 0.0,
            "barcode": None,
            "confidence_score": 0.96,
        }],
        parser_diagnostics={"test": True},
    )


def _request() -> ScanRequestV1:
    return ScanRequestV1.from_bytes(
        scan_id="rscan_release_a_test",
        file_bytes=b"receipt bytes",
        filename="kassabon.jpg",
        mime_type="image/jpeg",
    )


def _roundtrip(expected: ReceiptParseResult) -> tuple[CanonicalReceiptV1, ReceiptParseResult]:
    adapter = RezzervLegacyScannerAdapter(parser=lambda *_args: expected)
    request = _request()
    submission = adapter.submit(request)
    assert submission.status == "completed"
    canonical = validate_canonical_receipt(
        submission.result,
        expected_scan_id=request.scan_id,
        expected_sha256=request.document.sha256,
    )
    return canonical, canonical_to_receipt_parse_result(canonical)


def test_scan_request_does_not_serialize_document_bytes_or_household_context():
    request = _request()
    payload = request.model_dump(mode="json")
    serialized = str(payload)
    assert "receipt bytes" not in serialized
    assert "household_id" not in serialized
    assert "user" not in serialized
    assert payload["document"]["content_ref"].startswith("internal://receipt-scan/")


def test_legacy_adapter_roundtrip_preserves_existing_receipt_dto_semantics():
    expected = _legacy_result()
    _canonical, actual = _roundtrip(expected)
    assert actual.is_receipt is expected.is_receipt
    assert actual.parse_status == expected.parse_status
    assert actual.store_name == expected.store_name
    assert actual.store_branch == expected.store_branch
    assert actual.purchase_at == expected.purchase_at
    assert actual.total_amount == expected.total_amount
    assert actual.discount_total == expected.discount_total
    assert actual.currency == expected.currency
    assert actual.lines == expected.lines
    assert actual.parser_diagnostics == expected.parser_diagnostics
    assert isinstance(actual.lines[0]["quantity"], float)
    assert isinstance(actual.lines[0]["unit_price"], float)
    assert isinstance(actual.lines[0]["line_total"], float)
    assert isinstance(actual.lines[0]["discount_amount"], float)


def test_legacy_adapter_preserves_review_needed_receipt_without_total():
    expected = ReceiptParseResult(
        is_receipt=True,
        parse_status="review_needed",
        confidence_score=0.62,
        store_name="Lidl",
        store_branch="Arnhem",
        purchase_at="2026-02-19",
        total_amount=None,
        discount_total=Decimal("0.00"),
        currency="EUR",
        lines=[{
            "raw_label": "TOMATEN 2,99",
            "normalized_label": "Tomaten",
            "quantity": 1.0,
            "unit": "piece",
            "unit_price": 2.99,
            "line_total": 2.99,
            "discount_amount": 0.0,
            "barcode": None,
            "confidence_score": 0.75,
        }],
        parser_diagnostics={"reason": "total_unresolved"},
    )
    canonical, actual = _roundtrip(expected)
    assert canonical.quality is not None
    assert canonical.quality.requires_review is True
    assert actual.is_receipt is True
    assert actual.parse_status == "review_needed"
    assert actual.total_amount is None
    assert len(actual.lines or []) == 1
    assert isinstance(actual.lines[0]["unit_price"], float)


def test_legacy_adapter_preserves_parsed_receipt_without_article_lines():
    expected = ReceiptParseResult(
        is_receipt=True,
        parse_status="parsed",
        confidence_score=0.67,
        store_name="Lidl",
        store_branch="Arnhem",
        purchase_at="2026-02-19",
        total_amount=Decimal("33.80"),
        discount_total=Decimal("0.00"),
        currency="EUR",
        lines=[],
        parser_diagnostics={"reason": "articles_unresolved"},
    )
    canonical, actual = _roundtrip(expected)
    assert canonical.quality is not None
    assert canonical.quality.requires_review is True
    assert actual.is_receipt is True
    assert actual.parse_status == "parsed"
    assert actual.total_amount == Decimal("33.80")
    assert actual.lines == []


def test_contract_still_rejects_incomplete_receipt_when_review_is_not_required():
    payload = {
        "schema_version": "1.0",
        "scan_id": "rscan_strict_completed",
        "provider": {"code": "fake-test"},
        "status": "completed",
        "document": {"sha256": "d" * 64, "mime_type": "image/jpeg", "page_count": 1},
        "receipt": {
            "store": {"name": "Lidl"},
            "transaction": {"purchase_date": "2026-02-19", "currency": "EUR"},
            "totals": {"grand_total": None},
            "lines": [],
            "warnings": [],
        },
        "quality": {"overall_confidence": 0.95, "requires_review": False},
    }
    with pytest.raises(Exception):
        CanonicalReceiptV1.model_validate(payload)


def test_external_provider_canonical_line_numbers_are_sqlite_persistable():
    canonical = CanonicalReceiptV1(
        scan_id="rscan_external_persistence",
        provider={"code": "external-test", "job_id": "job-1", "result_id": "result-1"},
        status="completed",
        document={"sha256": "e" * 64, "mime_type": "image/jpeg", "page_count": 1},
        receipt={
            "store": {"name": "External Store"},
            "transaction": {"purchase_date": "2026-08-10", "currency": "EUR"},
            "totals": {"grand_total": "8.98"},
            "lines": [{
                "line_number": 1,
                "line_type": "product",
                "raw_text": "2 FAIRTRADE CHENIN BL 8,98",
                "description": "Fairtrade Chenin Bl",
                "quantity": "2",
                "unit_price": "4.49",
                "line_total": "8.98",
                "discount_amount": "0.00",
            }],
            "warnings": [],
        },
        quality={"overall_confidence": 0.95, "requires_review": False},
    )
    normalized = canonical_to_receipt_parse_result(canonical)
    line = normalized.lines[0]
    assert line["quantity"] == 2.0
    assert line["unit_price"] == 4.49
    assert line["line_total"] == 8.98
    assert line["discount_amount"] == 0.0
    assert all(
        value is None or isinstance(value, float)
        for value in (line["quantity"], line["unit_price"], line["line_total"], line["discount_amount"])
    )

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE receipt_line (quantity REAL, unit_price REAL, line_total REAL, discount_amount REAL)"))
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
        persisted = conn.execute(text("SELECT quantity, unit_price, line_total, discount_amount FROM receipt_line")).mappings().one()
    assert persisted["quantity"] == 2.0
    assert persisted["unit_price"] == 4.49
    assert persisted["line_total"] == 8.98
    assert persisted["discount_amount"] == 0.0


def test_legacy_failed_result_stays_failed_without_persistable_receipt_payload():
    expected = ReceiptParseResult(
        is_receipt=False,
        parse_status="failed",
        confidence_score=0.1,
        store_name=None,
        purchase_at=None,
        total_amount=None,
        discount_total=None,
        currency="EUR",
        lines=[],
        parser_diagnostics={"reason": "not_receipt"},
    )
    adapter = RezzervLegacyScannerAdapter(parser=lambda *_args: expected)
    submission = adapter.submit(_request())
    assert submission.status == "failed"
    assert submission.result is not None
    assert submission.result.receipt is None
    assert submission.result.error is not None
    assert submission.result.error.code == "NO_RECEIPT_DETECTED"
    actual = canonical_to_receipt_parse_result(submission.result)
    assert actual.is_receipt is False
    assert actual.parse_status == "failed"
    assert actual.confidence_score == 0.1
    assert actual.parser_diagnostics == {"reason": "not_receipt"}


def test_contract_rejects_duplicate_line_number():
    payload = {
        "schema_version": "1.0", "scan_id": "rscan_duplicate", "provider": {"code": "fake-test"}, "status": "completed",
        "document": {"sha256": "a" * 64, "mime_type": "image/jpeg", "page_count": 1},
        "receipt": {
            "store": {"name": "Test"}, "transaction": {"purchase_date": "2026-08-03", "currency": "EUR"},
            "totals": {"grand_total": "2.00"},
            "lines": [
                {"line_number": 1, "line_type": "product", "raw_text": "A", "line_total": "1.00"},
                {"line_number": 1, "line_type": "product", "raw_text": "B", "line_total": "1.00"},
            ], "warnings": [],
        },
        "quality": {"overall_confidence": 0.9, "requires_review": False},
    }
    with pytest.raises(Exception):
        CanonicalReceiptV1.model_validate(payload)


def test_contract_allows_forward_compatible_extra_fields():
    payload = {
        "schema_version": "1.0", "scan_id": "rscan_forward", "provider": {"code": "fake-test", "future_provider_field": "ok"}, "status": "completed",
        "document": {"sha256": "b" * 64, "mime_type": "image/jpeg", "page_count": 1, "future_document_field": True},
        "receipt": {
            "store": {"name": "Test"}, "transaction": {"purchase_date": "2026-08-03", "currency": "EUR"},
            "totals": {"grand_total": "1.00"},
            "lines": [{"line_number": 1, "line_type": "unknown", "raw_text": "onbekend", "line_total": "1.00", "future_line_field": 123}],
            "warnings": [], "future_receipt_field": "ok",
        },
        "quality": {"overall_confidence": None, "requires_review": True}, "future_root_field": "ok",
    }
    result = validate_canonical_receipt(payload)
    assert result.status == "completed"


def test_contract_rejects_only_payment_lines():
    payload = {
        "schema_version": "1.0", "scan_id": "rscan_payment", "status": "completed",
        "document": {"sha256": "c" * 64, "mime_type": "image/jpeg", "page_count": 1},
        "receipt": {
            "store": {"name": "Test"}, "transaction": {"purchase_date": "2026-08-03", "currency": "EUR"},
            "totals": {"grand_total": "1.00"},
            "lines": [{"line_number": 1, "line_type": "payment", "raw_text": "PIN 1,00", "line_total": "1.00"}], "warnings": [],
        },
        "quality": {"overall_confidence": 0.9, "requires_review": True},
    }
    with pytest.raises(Exception):
        CanonicalReceiptV1.model_validate(payload)


def test_gateway_supports_async_provider_state_transition():
    request = _request()
    sha = request.document.sha256
    queued = CanonicalReceiptV1(scan_id=request.scan_id, provider={"code": "fake-test", "job_id": "q1", "model_version": "fake-v1"}, status="queued")
    completed = CanonicalReceiptV1(
        scan_id=request.scan_id,
        provider={"code": "fake-test", "job_id": "q1", "result_id": "r1", "model_version": "fake-v1"},
        status="completed",
        document={"sha256": sha, "mime_type": "image/jpeg", "page_count": 1},
        receipt={
            "store": {"name": "Test"}, "transaction": {"purchase_date": "2026-08-03", "currency": "EUR"},
            "totals": {"grand_total": "1.00"},
            "lines": [{"line_number": 1, "line_type": "unknown", "raw_text": "TEST", "line_total": "1.00"}], "warnings": [],
        },
        quality={"overall_confidence": 0.5, "requires_review": True},
    )
    provider = FakeScannerProvider([queued, completed])
    gateway = ReceiptScannerGateway(ProviderRegistry([provider], active_provider_code="fake-test"), timeout_seconds=1, poll_interval_seconds=0)
    result = gateway.scan(request)
    assert result.status == "completed"
    assert result.scan_id == request.scan_id


def test_unknown_provider_is_fail_fast_configuration_error(monkeypatch):
    monkeypatch.setenv("REZZERV_RECEIPT_SCANNER_PROVIDER", "not-installed")
    reset_receipt_scanner_runtime_cache()
    with pytest.raises(ProviderConfigurationError):
        validate_receipt_scanner_configuration()
    monkeypatch.delenv("REZZERV_RECEIPT_SCANNER_PROVIDER", raising=False)
    reset_receipt_scanner_runtime_cache()


def test_production_ingest_and_reparse_use_gateway_not_direct_parser():
    source = Path(__file__).resolve().parents[1] / "app" / "services" / "receipt_service.py"
    text = source.read_text(encoding="utf-8")
    ingest_start = text.index("def ingest_receipt(")
    ingest_end = text.index("\ndef _resolve_reparse_source_payload", ingest_start)
    ingest_body = text[ingest_start:ingest_end]
    assert "scan_receipt_content_via_gateway(" in ingest_body
    assert "parse_receipt_content(" not in ingest_body
    reparse_start = text.index("def reparse_receipt(")
    reparse_end = text.index("\ndef scan_receipt_source", reparse_start)
    reparse_body = text[reparse_start:reparse_end]
    assert "scan_receipt_content_via_gateway(" in reparse_body
    assert "parse_receipt_content(" not in reparse_body
