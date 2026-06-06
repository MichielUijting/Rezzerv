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

"""Deprecated receipt debug artifact monkeypatch.

R9-36N4:
This module must not replace parser or ingest functions at import time. Debug
artifacts must be produced through explicit code paths in the normal ingest flow
or through dedicated diagnostic routes.
"""

from typing import Any

_LAST_PARSE_CAPTURE: dict[str, Any] = {}


def latest_parse_capture() -> dict[str, Any]:
    return dict(_LAST_PARSE_CAPTURE)


def install_receipt_debug_artifacts_patch(*_: Any) -> bool:
    """Compatibility no-op: do not mutate receipt_service."""
    return False
