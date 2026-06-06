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

"""
PLUS savings / zegels / PLUSPunten profile module.

R9-38C1a architecture anchor:
- PLUSPunten / PiUSPunten
- zegel / actie correcties
- savings norm-line interpretation

Runtime behavior is currently implemented in corrections.py to avoid behavior changes.
This file exists to make the PLUS profile structure explicit for the next safe split.
"""
