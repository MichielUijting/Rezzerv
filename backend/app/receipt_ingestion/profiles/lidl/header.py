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
"""Lidl header parsing extension points for R9-38A0."""



def parse_lidl_header(lines: list[str] | tuple[str, ...] | None) -> dict[str, object]:
    """Return Lidl header metadata placeholder.

    R9-38A0 is structure-only and returns no extracted metadata yet.
    """
    return {}
