from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.services.receipt_parser_diagnosis_route_cleanup import (
    deduplicate_receipt_parser_diagnosis_routes,
)

PROTECTED_MUTATIONS: set[tuple[str, str]] = set()


def authorize_platform_admin_request(
    method: str,
    path: str,
    authorization: str | None,
    require_platform_admin_user: Callable[[str | None], object],
) -> object | None:
    request_key = (str(method or "").upper(), str(path or ""))
    if request_key not in PROTECTED_MUTATIONS:
        return None
    return require_platform_admin_user(authorization)


def install_platform_admin_route_guard(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "platform_admin_route_guard_installed", False):
        return

    deduplicate_receipt_parser_diagnosis_routes(app)

    @app.middleware("http")
    async def platform_admin_route_guard(request, call_next):
        try:
            authorize_platform_admin_request(
                request.method,
                request.url.path,
                request.headers.get("authorization"),
                main_module.require_platform_admin_user,
            )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or None,
            )
        return await call_next(request)

    app.state.platform_admin_route_guard_installed = True
    app.state.receipt_admin_household_guard_installed = True
