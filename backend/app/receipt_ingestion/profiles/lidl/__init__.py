"""Lidl receipt profile package.

R9-38A0 introduces the modular Lidl profile frame only.
No functional parser behaviour is changed in this step.
"""

from .profile import (
    classify_lidl_line,
    detect_lidl_receipt_type,
    is_lidl_context,
    is_lidl_non_product_line,
)

__all__ = [
    "classify_lidl_line",
    "detect_lidl_receipt_type",
    "is_lidl_context",
    "is_lidl_non_product_line",
]
