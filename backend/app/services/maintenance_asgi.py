"""TD-02: outermost admission boundary, including response background tasks."""
from __future__ import annotations

import asyncio

from starlette.responses import JSONResponse

from .maintenance_runtime import _operation
from .maintenance_postgres_admission import admit_operation, complete_operation

# Exact infrastructure routes only. Domain GETs can write/backfill and therefore
# require admission too. No platform/admin-prefix exemption.
_INFRASTRUCTURE = frozenset({
    ("GET", "/api/health"), ("GET", "/api/version"), ("GET", "/api/session"),
    ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"),
    ("GET", "/api/features"), ("GET", "/api/notifications"),
    ("GET", "/api/maintenance/status"),
    ("GET", "/api/platform/maintenance"),
    ("POST", "/api/platform/maintenance"),
})


class MaintenanceAdmissionMiddleware:
    def __init__(self, app, engine):
        self.app, self.engine = app, engine

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS" or not scope["path"].startswith("/api/") or (scope["method"], scope["path"]) in _INFRASTRUCTURE:
            await self.app(scope, receive, send)
            return
        if self.engine.dialect.name != "postgresql":
            await self.app(scope, receive, send)
            return
        def reserve():
            with self.engine.begin() as conn:
                return admit_operation(conn, kind=("http:"+scope["method"]+" "+scope["path"])[:100])
        try:
            operation_id = await asyncio.to_thread(reserve)
        except Exception:
            response = JSONResponse(status_code=503, content={"detail":"Inhuis is tijdelijk geblokkeerd voor serveronderhoud. Niet-opgeslagen invoer is niet verwerkt.", "code":"INHUIS_MAINTENANCE"}, headers={"Retry-After":"15", "Cache-Control":"no-store"})
            await response(scope, receive, send)
            return
        token = _operation.set(operation_id)
        succeeded = False
        try:
            await self.app(scope, receive, send)
            succeeded = True
        finally:
            _operation.reset(token)
        if succeeded:
            def finish():
                with self.engine.begin() as conn:
                    complete_operation(conn, operation_id=operation_id)
            await asyncio.shield(asyncio.to_thread(finish))
