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
"""Read-only receipt parse context boundary."""


from dataclasses import dataclass


@dataclass(frozen=True)
class ReceiptSourceContext:
    filename: str
    mime_type: str | None = None
    source_kind: str | None = None