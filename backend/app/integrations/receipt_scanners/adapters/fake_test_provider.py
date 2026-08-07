from __future__ import annotations

import uuid
from collections import deque

from ..contracts import ScannerCapabilities, ScannerHealth
from ..errors import UnsupportedOperation
from ..schemas.canonical_receipt_v1 import CanonicalReceiptV1
from ..schemas.scan_request_v1 import ScanRequestV1
from ..schemas.scan_result_v1 import ScanResultV1, ScanSubmissionV1


class FakeScannerProvider:
    """Deterministic provider used by contract and gateway tests."""

    provider_code = "fake-test"

    def __init__(self, results: list[CanonicalReceiptV1]) -> None:
        if not results:
            raise ValueError("FakeScannerProvider requires at least one result")
        self._queue = deque(results)
        self._jobs: dict[str, CanonicalReceiptV1] = {}

    def capabilities(self) -> ScannerCapabilities:
        return ScannerCapabilities(
            mime_types=("image/jpeg", "image/png", "application/pdf", "text/plain"),
            max_file_bytes=15_000_000,
            asynchronous=True,
            supports_cancel=False,
            features=("contract_test",),
        )

    def submit(self, request: ScanRequestV1) -> ScanSubmissionV1:
        job_id = f"fake-{uuid.uuid4().hex}"
        first = self._queue[0]
        self._jobs[job_id] = first
        if first.status not in {"queued", "processing"}:
            self._queue.popleft()
            return ScanSubmissionV1(
                scan_id=request.scan_id,
                provider_job_id=job_id,
                status="completed" if first.status == "completed" else "failed",
                result=first,
            )
        return ScanSubmissionV1(
            scan_id=request.scan_id,
            provider_job_id=job_id,
            status=first.status,
            result=None,
        )

    def get_result(self, provider_job_id: str) -> ScanResultV1:
        if provider_job_id not in self._jobs:
            raise KeyError(provider_job_id)
        if self._queue:
            result = self._queue.popleft()
            self._jobs[provider_job_id] = result
            return result
        return self._jobs[provider_job_id]

    def cancel(self, provider_job_id: str) -> None:
        raise UnsupportedOperation("FakeScannerProvider cancellation is not configured")

    def health(self) -> ScannerHealth:
        return ScannerHealth(
            available=True,
            provider_code=self.provider_code,
            contract_version="1.0",
            model_version="fake-v1",
        )
