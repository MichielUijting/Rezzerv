from __future__ import annotations

from pydantic import ValidationError

from .errors import ContractValidationError
from .schemas.canonical_receipt_v1 import CanonicalReceiptV1


def validate_canonical_receipt(
    value: CanonicalReceiptV1 | dict,
    *,
    expected_scan_id: str | None = None,
    expected_sha256: str | None = None,
) -> CanonicalReceiptV1:
    """Validate the provider-neutral contract before Rezzerv persistence."""

    try:
        result = value if isinstance(value, CanonicalReceiptV1) else CanonicalReceiptV1.model_validate(value)
    except ValidationError as exc:
        raise ContractValidationError(f"CanonicalReceiptV1 validation failed: {exc}") from exc

    if expected_scan_id is not None and result.scan_id != expected_scan_id:
        raise ContractValidationError(
            f"Provider returned scan_id {result.scan_id!r}; expected {expected_scan_id!r}"
        )

    if (
        expected_sha256 is not None
        and result.document is not None
        and result.document.sha256.lower() != expected_sha256.lower()
    ):
        raise ContractValidationError("Provider returned a document SHA-256 that does not match the input")

    return result
