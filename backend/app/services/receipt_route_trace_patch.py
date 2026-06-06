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

"""Deprecated route tracing monkeypatch.

R9-36N4:
This module must not replace FastAPI internals. Upload diagnostics must be
implemented through explicit middleware, route dependencies, or normal logging
inside the relevant route handlers. Importing this module may not mutate
``APIRoute.get_route_handler``.
"""

from typing import Any

_INSTALLED = False


def install_receipt_route_trace_patch(*_: Any) -> bool:
    """Compatibility no-op: do not patch FastAPI runtime internals."""
    return False
