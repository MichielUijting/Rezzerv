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

"""Service package marker.

R9-36N:
This package initializer must not mutate receipt parsing behavior.

Historically this module installed runtime monkeypatches on
``app.services.receipt_service`` when the ``app.services`` package was imported.
That made parser behavior depend on import order: importing ``app.main`` could
change ``parse_receipt_content`` and related helpers, while a direct import of
``app.services.receipt_service`` could produce a different result.

Receipt ingestion must be explicit and deterministic. Image preprocessing remains
inside the normal receipt parser flow; no package-level monkeypatching is allowed
from this module.
"""

__all__: list[str] = []
