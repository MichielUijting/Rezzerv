from __future__ import annotations

import time

from .diagnostics import ScanDiagnostics
from .errors import ProviderTimeoutError, ReceiptScannerError
from .registry import ProviderRegistry
from .schemas.canonical_receipt_v1 import CanonicalReceiptV1
from .schemas.scan_request_v1 import ScanRequestV1
from .validator import validate_canonical_receipt


class ReceiptScannerGateway:
    """Provider-neutral orchestration boundary before Kassa persistence."""

    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        timeout_seconds: float = 90.0,
        poll_interval_seconds: float = 0.05,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.registry = registry
        self.timeout_seconds = float(timeout_seconds)
        self.poll_interval_seconds = max(0.0, float(poll_interval_seconds))

    def scan(self, request: ScanRequestV1) -> CanonicalReceiptV1:
        provider = self.registry.get()
        capabilities = provider.capabilities()
        diagnostics = ScanDiagnostics(request.scan_id, provider.provider_code)

        if request.document.mime_type not in capabilities.mime_types:
            raise ReceiptScannerError(
                f"Provider {provider.provider_code!r} does not support {request.document.mime_type}",
                code="UNSUPPORTED_FORMAT",
            )
        if request.document.size_bytes > capabilities.max_file_bytes:
            raise ReceiptScannerError(
                f"Document exceeds provider limit of {capabilities.max_file_bytes} bytes",
                code="DOCUMENT_TOO_LARGE",
            )

        submission = provider.submit(request)
        deadline = time.monotonic() + self.timeout_seconds
        result = submission.result

        while result is None:
            if submission.status == "failed":
                raise ReceiptScannerError("Provider submission failed", code="PROVIDER_UNAVAILABLE")
            if time.monotonic() >= deadline:
                try:
                    provider.cancel(submission.provider_job_id)
                except Exception:
                    pass
                raise ProviderTimeoutError(
                    f"Receipt scanner provider {provider.provider_code!r} exceeded timeout"
                )
            if self.poll_interval_seconds:
                time.sleep(self.poll_interval_seconds)
            result = provider.get_result(submission.provider_job_id)
            if result.status in {"queued", "processing"}:
                result = None
                continue

        validated = validate_canonical_receipt(
            result,
            expected_scan_id=request.scan_id,
            expected_sha256=request.document.sha256,
        )
        receipt = validated.receipt
        diagnostics.log_result(
            status=validated.status,
            model_version=validated.provider.model_version if validated.provider else None,
            warning_count=len(receipt.warnings) if receipt else 0,
            review_required=validated.quality.requires_review if validated.quality else None,
            sha256_prefix=request.document.sha256[:12],
        )
        return validated
