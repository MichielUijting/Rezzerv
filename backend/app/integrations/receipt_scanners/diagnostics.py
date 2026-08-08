from __future__ import annotations

import logging
from time import monotonic

LOGGER = logging.getLogger("rezzerv.receipt_scanners")


class ScanDiagnostics:
    """Metadata-only scanner diagnostics; never log receipt text or document bytes."""

    def __init__(self, scan_id: str, provider_code: str, contract_version: str = "1.0") -> None:
        self.scan_id = scan_id
        self.provider_code = provider_code
        self.contract_version = contract_version
        self.started = monotonic()

    def log_result(
        self,
        *,
        status: str,
        model_version: str | None,
        warning_count: int = 0,
        review_required: bool | None = None,
        mapping_error_code: str | None = None,
        sha256_prefix: str | None = None,
    ) -> None:
        LOGGER.info(
            "receipt_scan scan_id=%s provider=%s model=%s contract=%s duration_ms=%d "
            "status=%s validation_warning_count=%d review_required=%s mapping_error_code=%s sha256_prefix=%s",
            self.scan_id,
            self.provider_code,
            model_version or "-",
            self.contract_version,
            int((monotonic() - self.started) * 1000),
            status,
            int(warning_count),
            review_required,
            mapping_error_code or "-",
            sha256_prefix or "-",
        )
