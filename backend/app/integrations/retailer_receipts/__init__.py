"""Provider-neutral import boundary for structured digital supermarket receipts."""

from .contracts import (
    RETAILER_RECEIPT_MIME,
    SUPPORTED_RETAILER_PROVIDERS,
    RetailerReceiptEnvelope,
)
from .normalizer import normalize_retailer_receipt

__all__ = [
    "RETAILER_RECEIPT_MIME",
    "SUPPORTED_RETAILER_PROVIDERS",
    "RetailerReceiptEnvelope",
    "normalize_retailer_receipt",
]
