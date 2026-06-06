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

from __future__ import annotations

import re


def normalize_text_lines(text: str) -> list[str]:
    """Normalize extracted OCR/PDF/e-mail text into non-empty receipt lines.

    This is a behavior-preserving extraction from receipt_service.py. It is kept
    deliberately small and side-effect free so the generic parser boundary can
    move toward receipt_ingestion without touching parser behavior or status.
    """
    raw_lines = re.split(r'\r?\n+', text)
    lines: list[str] = []
    for line in raw_lines:
        normalized = re.sub(r'\s+', ' ', line).strip()
        if normalized:
            lines.append(normalized)
    return lines
