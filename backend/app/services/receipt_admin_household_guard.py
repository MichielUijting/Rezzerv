from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException
from fastapi.responses import JSONResponse

_PROTECTED_METHOD = "POST"
_PROTECTED_PATHS = {
    "/api/admin/recompute-receipt-statuses",
    "/api/admin/validate-receipt-status-baseline",
    "/api/admin/diagnose-receipt-status-baseline",
}


def authorize_receipt_admin_request(
    method: str,
    path: str,
    authorization: str | None,
    require_platform_admin_user: Callable[[str | None], object],
) -> object | None:
    if str(method or "").upper() != _PROTECTED_METHOD:
        return None
    if str(path or "") not in _PROTECTED_PATHS:
        return None
    return require_platform_admin_user(authorization)


def install_receipt_admin_household_guard(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "receipt_admin_household_guard_installed", False):
        return

    @app.middleware("http")
    async def receipt_admin_household_guard(request, call_next):
        try:
            authorize_receipt_admin_request(
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

    app.state.receipt_admin_household_guard_installed = True
