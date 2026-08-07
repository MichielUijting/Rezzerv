from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .schemas.scan_request_v1 import ScanRequestV1
from .schemas.scan_result_v1 import ScanResultV1, ScanSubmissionV1


class ScannerCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mime_types: tuple[str, ...]
    max_file_bytes: int = Field(gt=0)
    asynchronous: bool = False
    supports_cancel: bool = False
    features: tuple[str, ...] = ()


class ScannerHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    provider_code: str
    contract_version: str = "1.0"
    model_version: str | None = None
    message: str | None = None


class ReceiptScannerProvider(Protocol):
    provider_code: str

    def capabilities(self) -> ScannerCapabilities: ...
    def submit(self, request: ScanRequestV1) -> ScanSubmissionV1: ...
    def get_result(self, provider_job_id: str) -> ScanResultV1: ...
    def cancel(self, provider_job_id: str) -> None: ...
    def health(self) -> ScannerHealth: ...
