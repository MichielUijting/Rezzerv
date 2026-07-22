from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException
from fastapi.responses import JSONResponse

_PROTECTED_REQUESTS = {
    ("POST", "/api/admin/backfill-purchase-import-live-aliases"),
    ("POST", "/api/admin/recompute-receipt-statuses"),
    ("POST", "/api/admin/validate-receipt-status-baseline"),
    ("POST", "/api/admin/diagnose-receipt-status-baseline"),
    ("POST", "/api/testing/fixtures/receipt-export/generate"),
    ("GET", "/api/testing/fixtures/receipt-export/download"),
    ("POST", "/api/testing/diagnostics/store-location-options"),
}


def authorize_receipt_admin_request(
    method: str,
    path: str,
    authorization: str | None,
    require_platform_admin_user: Callable[[str | None], object],
) -> object | None:
    request_key = (str(method or "").upper(), str(path or ""))
    if request_key not in _PROTECTED_REQUESTS:
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
