from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException
from fastapi.responses import JSONResponse

_PROTECTED_METHOD = "POST"
_PROTECTED_PATH = "/api/receipts/share-import"


async def authorize_receipt_share_import_request(
    request,
    require_household_context: Callable[[str | None, str | None], dict[str, Any]],
) -> dict[str, Any] | None:
    """Authorize the authenticated share-import route against form household_id."""

    if str(request.method or "").upper() != _PROTECTED_METHOD:
        return None
    if str(request.url.path or "") != _PROTECTED_PATH:
        return None

    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Ongeldige share-import aanvraag") from exc

    household_id = str(form.get("household_id") or "").strip()
    if not household_id:
        raise HTTPException(status_code=400, detail="household_id is verplicht")

    return require_household_context(
        request.headers.get("authorization"),
        household_id,
    )


def install_receipt_share_import_household_guard(main_module) -> None:
    """Install an HTTP guard before receipt share-import source or receipt creation."""

    app = main_module.app
    if getattr(app.state, "receipt_share_import_household_guard_installed", False):
        return

    @app.middleware("http")
    async def receipt_share_import_household_guard(request, call_next):
        try:
            await authorize_receipt_share_import_request(
                request,
                main_module.require_household_context,
            )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or None,
            )
        return await call_next(request)

    app.state.receipt_share_import_household_guard_installed = True
