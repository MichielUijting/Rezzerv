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

"""Lidl filter extension points for R9-38A0."""

from __future__ import annotations


def is_lidl_non_product_line(line: str | None, *, context: object | None = None) -> bool:
    """Return whether a Lidl line is a known non-product line.

    R9-38A0 is a frame-only step. The default keeps all current lines in flow.
    """
    return False
