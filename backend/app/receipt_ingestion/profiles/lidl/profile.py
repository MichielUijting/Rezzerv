"""Lidl receipt profile frame.

R9-38A0 creates the modular profile surface only. The active parser flow is
not changed by this package until later diagnostic-driven steps wire proven
rules deliberately.
"""

from __future__ import annotations

from .articles import LidlLineClassification, classify_lidl_line
from .detect import LidlReceiptType, detect_lidl_receipt_type, is_lidl_context
from .filters import is_lidl_non_product_line

__all__ = [
    "LidlLineClassification",
    "LidlReceiptType",
    "classify_lidl_line",
    "detect_lidl_receipt_type",
    "is_lidl_context",
    "is_lidl_non_product_line",
]
