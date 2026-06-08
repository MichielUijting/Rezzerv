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
"""Albert Heijn profile metadata boundary.

R9-36A hard reset: no active AH parser rules are exposed from this module.
"""


CHAIN_ID = "ah"
DISPLAY_NAME = "Albert Heijn"
ACTIVE_RULES = False
