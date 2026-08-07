from __future__ import annotations

import os
import uuid
from functools import lru_cache

from app.receipt_ingestion.service_parts.receipt_result_helpers import ReceiptParseResult

from .adapters.rezzerv_legacy import RezzervLegacyScannerAdapter
from .errors import ProviderConfigurationError
from .gateway import ReceiptScannerGateway
from .normalizer import canonical_to_receipt_parse_result
from .registry import ProviderRegistry
from .schemas.scan_request_v1 import ScanRequestV1

DEFAULT_PROVIDER = "rezzerv-legacy"
DEFAULT_TIMEOUT_SECONDS = 90.0
DEFAULT_MAX_FILE_BYTES = 15_000_000
CONTRACT_VERSION = "1.0"


def _configured_provider_code() -> str:
    return str(os.getenv("REZZERV_RECEIPT_SCANNER_PROVIDER", DEFAULT_PROVIDER) or DEFAULT_PROVIDER).strip()


def _configured_timeout_seconds() -> float:
    raw = str(os.getenv("REZZERV_RECEIPT_SCANNER_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ProviderConfigurationError("REZZERV_RECEIPT_SCANNER_TIMEOUT_SECONDS must be numeric") from exc
    if value <= 0:
        raise ProviderConfigurationError("REZZERV_RECEIPT_SCANNER_TIMEOUT_SECONDS must be positive")
    return value


def _configured_max_file_bytes() -> int:
    raw = str(os.getenv("REZZERV_RECEIPT_SCANNER_MAX_FILE_BYTES", DEFAULT_MAX_FILE_BYTES))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ProviderConfigurationError("REZZERV_RECEIPT_SCANNER_MAX_FILE_BYTES must be an integer") from exc
    if value <= 0:
        raise ProviderConfigurationError("REZZERV_RECEIPT_SCANNER_MAX_FILE_BYTES must be positive")
    return value


def validate_receipt_scanner_configuration() -> None:
    contract_version = str(os.getenv("REZZERV_RECEIPT_SCANNER_CONTRACT_VERSION", CONTRACT_VERSION) or CONTRACT_VERSION).strip()
    if contract_version != CONTRACT_VERSION:
        raise ProviderConfigurationError(
            f"Unsupported REZZERV_RECEIPT_SCANNER_CONTRACT_VERSION={contract_version!r}; Release A supports {CONTRACT_VERSION!r}"
        )
    provider_code = _configured_provider_code()
    if provider_code != DEFAULT_PROVIDER:
        raise ProviderConfigurationError(
            f"Unknown receipt scanner provider {provider_code!r}; Release A provides {DEFAULT_PROVIDER!r} only"
        )
    _configured_timeout_seconds()
    _configured_max_file_bytes()


@lru_cache(maxsize=1)
def get_receipt_scanner_gateway() -> ReceiptScannerGateway:
    validate_receipt_scanner_configuration()
    provider = RezzervLegacyScannerAdapter(max_file_bytes=_configured_max_file_bytes())
    registry = ProviderRegistry([provider], active_provider_code=_configured_provider_code())
    return ReceiptScannerGateway(registry, timeout_seconds=_configured_timeout_seconds())


def reset_receipt_scanner_runtime_cache() -> None:
    get_receipt_scanner_gateway.cache_clear()


def scan_receipt_content_via_gateway(file_bytes: bytes, filename: str, mime_type: str) -> ReceiptParseResult:
    scan_id = f"rscan_{uuid.uuid4().hex}"
    request = ScanRequestV1.from_bytes(scan_id=scan_id, file_bytes=file_bytes, filename=filename, mime_type=mime_type)
    canonical = get_receipt_scanner_gateway().scan(request)
    return canonical_to_receipt_parse_result(canonical)
