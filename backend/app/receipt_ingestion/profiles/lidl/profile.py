"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

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
