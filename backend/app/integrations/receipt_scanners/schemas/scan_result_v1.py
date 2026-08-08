from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .canonical_receipt_v1 import CanonicalReceiptV1


class ScanSubmissionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    scan_id: str
    provider_job_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    result: CanonicalReceiptV1 | None = None


ScanResultV1 = CanonicalReceiptV1
