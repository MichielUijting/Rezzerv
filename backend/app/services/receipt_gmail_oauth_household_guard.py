from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException
from fastapi.responses import JSONResponse

_CONNECT_METHOD = "GET"
_CONNECT_PATH = "/api/receipts/gmail/connect-url"
_CALLBACK_METHOD = "GET"
_CALLBACK_PATH = "/api/receipts/gmail/callback"


def require_explicit_gmail_state_household(
    state: str | None,
    verify_gmail_state: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Verify Gmail OAuth state and reject missing or ambiguous household scope."""

    payload = verify_gmail_state(str(state or ""))
    provider = str(payload.get("provider") or "").strip().lower()
    household_id = str(payload.get("household_id") or "").strip()
    if provider != "gmail":
        raise HTTPException(status_code=400, detail="Ongeldige Gmail OAuth-state")
    if not household_id:
        raise HTTPException(status_code=400, detail="Huishouden ontbreekt in Gmail OAuth-state")
    return payload


def install_receipt_gmail_oauth_household_guard(main_module) -> None:
    """Protect Gmail connect initiation and fail closed on callback household scope."""

    app = main_module.app
    if getattr(app.state, "receipt_gmail_oauth_household_guard_installed", False):
        return

    @app.middleware("http")
    async def receipt_gmail_oauth_household_guard(request, call_next):
        method = str(request.method or "").upper()
        path = str(request.url.path or "")
        try:
            if method == _CONNECT_METHOD and path == _CONNECT_PATH:
                household_id = str(request.query_params.get("householdId") or "").strip()
                if not household_id:
                    raise HTTPException(status_code=400, detail="householdId is verplicht")
                main_module.require_household_admin_context(
                    request.headers.get("authorization"),
                    household_id,
                )
            elif method == _CALLBACK_METHOD and path == _CALLBACK_PATH:
                require_explicit_gmail_state_household(
                    request.query_params.get("state"),
                    main_module.verify_gmail_state,
                )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or None,
            )
        return await call_next(request)

    app.state.receipt_gmail_oauth_household_guard_installed = True
