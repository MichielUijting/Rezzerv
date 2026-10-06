from __future__ import annotations

import hashlib

import httpx
import pytest

from app.integrations.receipt_scanners.adapters.in_huis_demo import InHuisDemoScannerAdapter
from app.integrations.receipt_scanners.errors import ProviderConfigurationError
from app.integrations.receipt_scanners.runtime import _gateway_for_provider
from app.integrations.receipt_scanners.schemas.scan_request_v1 import ScanRequestV1


def _request() -> ScanRequestV1:
    return ScanRequestV1.from_bytes(
        scan_id="rscan_external_test",
        file_bytes=b"external receipt bytes",
        filename="receipt.jpg",
        mime_type="image/jpeg",
    )


def _completed_payload(request: ScanRequestV1) -> dict:
    return {
        "schema_version": "1.0",
        "scan_id": request.scan_id,
        "provider": {
            "code": "in-huis-demo",
            "job_id": "job-1",
            "result_id": "result-1",
            "model_version": "demo-1",
        },
        "status": "completed",
        "document": {
            "sha256": request.document.sha256,
            "mime_type": request.document.mime_type,
            "page_count": 1,
        },
        "receipt": {
            "store": {"name": "Testwinkel", "confidence": 0.9},
            "transaction": {"purchase_date": "2026-10-06", "currency": "EUR", "confidence": 0.9},
            "totals": {"grand_total": "2.78", "paid_total": "2.78", "confidence": 0.9},
            "lines": [{
                "line_number": 1,
                "line_type": "product",
                "raw_text": "MELK 2,78",
                "description": "Melk",
                "quantity": "2",
                "unit": "piece",
                "unit_price": "1.39",
                "line_total": "2.78",
            }],
            "warnings": [],
        },
        "quality": {"overall_confidence": 0.9, "requires_review": False},
        "processed_at": "2026-10-06T01:00:00Z",
    }


def test_household_provider_defaults_to_inhuis_gateway():
    gateway = _gateway_for_provider("inhuis")
    assert gateway.registry.active_provider_code == "rezzerv-legacy"


def test_alternative_provider_requires_configured_base_url(monkeypatch):
    monkeypatch.delenv("REZZERV_IN_HUIS_DEMO_SCANNER_BASE_URL", raising=False)
    with pytest.raises(ProviderConfigurationError):
        _gateway_for_provider("in-huis-demo")


def test_external_provider_posts_testkit_multipart_contract_and_accepts_sync_result():
    request = _request()

    def handler(http_request: httpx.Request) -> httpx.Response:
        assert http_request.method == "POST"
        assert http_request.url.path == "/scan"
        assert http_request.headers["x-api-key"] == "secret"
        body = http_request.content
        assert b'name="scan_id"' in body
        assert request.scan_id.encode() in body
        assert b'name="schema_version"' in body
        assert b'name="locale"' in body
        assert b'name="currency"' in body
        assert b'name="document_sha256"' in body
        assert request.document.sha256.encode() in body
        assert b'name="file"; filename="receipt.jpg"' in body
        assert request.runtime_document_bytes() in body
        return httpx.Response(200, json=_completed_payload(request))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = InHuisDemoScannerAdapter(
            base_url="https://scanner.example.test",
            api_key="secret",
            client=client,
        )
        submission = provider.submit(request)

    assert submission.status == "completed"
    assert submission.provider_job_id == "job-1"
    assert submission.result is not None
    assert submission.result.scan_id == request.scan_id
    assert submission.result.document.sha256 == hashlib.sha256(request.runtime_document_bytes()).hexdigest()


def test_external_provider_supports_202_and_poll_contract():
    request = _request()
    calls: list[str] = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        calls.append(f"{http_request.method} {http_request.url.path}")
        if http_request.method == "POST":
            return httpx.Response(202, json={
                "schema_version": "1.0",
                "scan_id": request.scan_id,
                "provider": {"code": "in-huis-demo", "job_id": "job async/1"},
                "status": "queued",
            })
        assert http_request.url.path == "/scan/job%20async%2F1"
        return httpx.Response(200, json=_completed_payload(request))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = InHuisDemoScannerAdapter(
            base_url="https://scanner.example.test",
            client=client,
        )
        submission = provider.submit(request)
        assert submission.status == "queued"
        assert submission.result is None
        result = provider.get_result(submission.provider_job_id)

    assert result.status == "completed"
    assert calls == ["POST /scan", "GET /scan/job%20async%2F1"]
