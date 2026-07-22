from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

_PROTECTED_METHOD = "POST"
_PROTECTED_PATHS = {
    "/api/products/enrich",
    "/api/products/enrich/retry",
}


def extract_requested_household_id(body: bytes) -> str | None:
    if not body:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("household_id")
    return str(value).strip() if value not in (None, "") else None


def authorize_product_enrichment_request(
    method: str,
    path: str,
    authorization: str | None,
    body: bytes,
    require_inventory_write_context: Callable[[str | None, str | None], dict[str, Any]],
) -> dict[str, Any] | None:
    if str(method or "").strip().upper() != _PROTECTED_METHOD:
        return None
    if str(path or "").strip() not in _PROTECTED_PATHS:
        return None
    requested_household_id = extract_requested_household_id(body)
    return require_inventory_write_context(authorization, requested_household_id)


def install_product_enrichment_write_guard(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "product_enrichment_write_guard_installed", False):
        return

    @app.middleware("http")
    async def product_enrichment_write_guard(request, call_next):
        try:
            body = await request.body()
            authorize_product_enrichment_request(
                request.method,
                request.url.path,
                request.headers.get("authorization"),
                body,
                main_module.require_inventory_write_context,
            )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or None,
            )
        return await call_next(request)

    app.state.product_enrichment_write_guard_installed = True
