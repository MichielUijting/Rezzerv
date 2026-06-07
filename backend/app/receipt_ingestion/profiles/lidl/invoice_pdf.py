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

"""Lidl PDF extension point for R9-38A0."""

from __future__ import annotations


def is_lidl_pdf_context(value: object | None = None) -> bool:
    """R9-38A0 placeholder."""
    return False
