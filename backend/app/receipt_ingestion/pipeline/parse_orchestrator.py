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

"""Generic parse orchestration skeleton.

R9-35A introduces the package boundary only. Runtime parsing remains unchanged
until a dedicated migration step moves existing code into this module.
"""

from __future__ import annotations


def orchestration_boundary() -> str:
    return 'receipt_ingestion.pipeline'