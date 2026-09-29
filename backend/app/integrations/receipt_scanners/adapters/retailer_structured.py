"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: ReceiptScannerProvider adapter for structured retailer receipts
- Runtime Type: production
- Used By: receipt scanner runtime
- Depends On: retailer receipt normalizer
- Reads Data: no
- Writes Data: no
- Status Authority: no
- Refactor Status: keep
"""

from __future__ import annotations

import json
import uuid

from app.integrations.retailer_receipts import (
    RETAILER_RECEIPT_MIME,
    RetailerReceiptEnvelope,
    normalize_retailer_receipt,
)

from ..contracts import ScannerCapabilities, ScannerHealth
from ..errors import UnsupportedOperation
from ..schemas.scan_request_v1 import ScanRequestV1
from ..schemas.scan_result_v1 import ScanResultV1, ScanSubmissionV1


class StructuredRetailerReceiptScannerAdapter:
    """Synchronous adapter from retailer JSON into CanonicalReceiptV1."""

    provider_code = "retailer-digital-receipt"

    def __init__(self, *, max_file_bytes: int = 2_000_000) -> None:
        self.max_file_bytes = int(max_file_bytes)
        self._results: dict[str, ScanResultV1] = {}

    def capabilities(self) -> ScannerCapabilities:
        return ScannerCapabilities(
            mime_types=(RETAILER_RECEIPT_MIME,),
            max_file_bytes=self.max_file_bytes,
            asynchronous=False,
            supports_cancel=False,
            features=("structured_receipt", "ah", "jumbo", "lidl"),
        )

    def submit(self, request: ScanRequestV1) -> ScanSubmissionV1:
        payload = json.loads(request.runtime_document_bytes().decode("utf-8"))
        envelope = RetailerReceiptEnvelope.model_validate(payload)
        result = normalize_retailer_receipt(
            envelope,
            scan_id=request.scan_id,
            document_sha256=request.document.sha256,
        )
        job_id = f"retailer-{uuid.uuid4().hex}"
        self._results[job_id] = result
        return ScanSubmissionV1(
            scan_id=request.scan_id,
            provider_job_id=job_id,
            status="completed",
            result=result,
        )

    def get_result(self, provider_job_id: str) -> ScanResultV1:
        return self._results[provider_job_id]

    def cancel(self, provider_job_id: str) -> None:
        raise UnsupportedOperation("Structured retailer import is synchronous and cannot be cancelled")

    def health(self) -> ScannerHealth:
        return ScannerHealth(
            available=True,
            provider_code=self.provider_code,
            contract_version="1.0",
            model_version="retailer-receipt-v1",
        )
