from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Header, HTTPException

from app.db import engine
from app.services.barcode_identity_service import lookup_gtin, validate_barcode

router = APIRouter(prefix="/api/barcodes", tags=["barcodes"])
_require_authenticated_context: Callable[..., dict] | None = None


def configure_barcode_routes(*, require_authenticated_context: Callable[..., dict]) -> None:
    global _require_authenticated_context
    _require_authenticated_context = require_authenticated_context


def _require_auth(authorization: str | None) -> dict:
    if _require_authenticated_context is None:
        raise RuntimeError("Barcode-routes zijn niet geconfigureerd")
    return _require_authenticated_context(authorization)


@router.post("/validate")
def barcode_validate(
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: Optional[str] = Header(None),
):
    _require_auth(authorization)
    return validate_barcode(
        payload.get("value"),
        str(payload.get("declared_type") or "gtin"),
    )


@router.get("/{gtin}")
def barcode_lookup(
    gtin: str,
    authorization: Optional[str] = Header(None),
):
    _require_auth(authorization)
    try:
        with engine.begin() as conn:
            return lookup_gtin(conn, gtin)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail="Barcode kon niet worden opgezocht") from exc
