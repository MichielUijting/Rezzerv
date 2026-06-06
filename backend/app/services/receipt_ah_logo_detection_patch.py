"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

"""Deprecated AH logo detection monkeypatch.

R9-36N4:
This module must not replace ``receipt_service.parse_receipt_content`` at import
time. Visual AH detection, if still needed, must be implemented as an explicitly
called helper inside the normal image receipt flow.
"""

from typing import Any


def install_receipt_ah_logo_detection_patch(*_: Any) -> bool:
    """Compatibility no-op: do not mutate receipt parser runtime."""
    return False
