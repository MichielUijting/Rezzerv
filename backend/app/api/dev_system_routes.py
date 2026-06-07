"""
Technical Design Reference:
- TD Section: TD-07 Diagnose en explainability
- Module Role: Diagnostic or test API route
- Runtime Type: diagnostic
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: keep_diagnostic
"""

from __future__ import annotations

from typing import Callable, Optional

from fastapi import APIRouter, Header


def create_dev_system_router(
    *,
    require_platform_admin_user: Callable[[Optional[str]], object],
    count_table: Callable[[str], int],
) -> APIRouter:
    router = APIRouter()

    @router.get('/api/dev/status')
    def get_dev_status(authorization: Optional[str] = Header(None)):
        require_platform_admin_user(authorization)
        return {
            'spaces': count_table('spaces'),
            'sublocations': count_table('sublocations'),
            'inventory': count_table('inventory'),
        }

    return router
