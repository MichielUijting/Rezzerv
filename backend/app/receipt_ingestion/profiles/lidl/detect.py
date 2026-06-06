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

"""Lidl receipt detection helpers.

R9-38A0: skeleton only.
These helpers expose stable extension points for later Lidl-specific logic,
but must not remove lines or decide functional status.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

LidlReceiptType = Literal["unknown", "ocr_photo", "app_pdf", "invoice_pdf"]


def _iter_text(lines_or_text: str | Iterable[str] | None) -> Iterable[str]:
    """Yield normalized text fragments from text or line collections."""
    if lines_or_text is None:
        return []
    if isinstance(lines_or_text, str):
        return lines_or_text.splitlines() or [lines_or_text]
    return lines_or_text


def is_lidl_context(lines_or_text: str | Iterable[str] | None) -> bool:
    """Return whether the supplied receipt context appears to be Lidl.

    Skeleton behaviour is intentionally conservative and side-effect free.
    Later steps may harden this using Lidl-specific evidence from diagnostics.
    """
    for line in _iter_text(lines_or_text):
        if "lidl" in str(line).casefold():
            return True
    return False


def detect_lidl_receipt_type(lines_or_text: str | Iterable[str] | None) -> LidlReceiptType:
    """Classify the broad Lidl source type without changing parser behaviour.

    R9-38A0 deliberately returns only a coarse default until R9-38A1
    diagnostics prove which Lidl variants must be supported.
    """
    if not is_lidl_context(lines_or_text):
        return "unknown"
    return "unknown"
