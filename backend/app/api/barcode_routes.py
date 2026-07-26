from __future__ import annotations
from app.services.off_product_link_service import save_barcode_receipt_item

from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Header, HTTPException

from app.db import engine
from app.services.barcode_identity_service import (
    BarcodeHouseholdArticleLinkError,
    link_household_article_to_matched_product,
    lookup_gtin,
    save_gtin_catalog_and_household_link,
    validate_barcode,
)
from app.services.household_context_adapter import (
    household_context_from_runtime_context,
)

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



@router.post("/{gtin}/household-article-link")
def barcode_household_article_link(
    gtin: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: Optional[str] = Header(None),
):
    runtime_context = _require_auth(authorization)
    household_context = household_context_from_runtime_context(
        runtime_context
    )

    if household_context.role == "viewer":
        raise HTTPException(
            status_code=403,
            detail="Alleen een lid of beheerder mag artikelen koppelen.",
        )

    try:
        with engine.begin() as conn:
            return link_household_article_to_matched_product(
                conn,
                household_id=household_context.active_household_id,
                purchase_import_line_id=str(
                    payload.get("purchase_import_line_id") or ""
                ),
                household_article_id=str(
                    payload.get("household_article_id") or ""
                ),
                gtin=gtin,
                global_product_id=str(
                    payload.get("global_product_id") or ""
                ),
            )
    except BarcodeHouseholdArticleLinkError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=500,
            detail="Barcodekoppeling kon niet worden opgeslagen",
        ) from exc



@router.post("/{gtin}/save-receipt-item")
def save_barcode_for_receipt_item(
    gtin: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: Optional[str] = Header(None),
):
    runtime_context = _require_auth(authorization)
    household_context = household_context_from_runtime_context(
        runtime_context
    )

    if household_context.role == "viewer":
        raise HTTPException(
            status_code=403,
            detail="Alleen een lid of beheerder mag barcodes opslaan.",
        )

    try:
        return save_barcode_receipt_item(
            household_id=household_context.active_household_id,
            receipt_item_id=str(
                payload.get("receipt_item_id") or ""
            ),
            gtin=gtin,
            article_name=str(
                payload.get("article_name") or ""
            ),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=500,
            detail="De barcode kon niet aan het kassabonartikel worden gekoppeld.",
        ) from exc


@router.post("/{gtin}/save-household-article")
def save_barcode_for_household_article(
    gtin: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: Optional[str] = Header(None),
):
    runtime_context = _require_auth(authorization)
    household_context = household_context_from_runtime_context(
        runtime_context
    )

    if household_context.role == "viewer":
        raise HTTPException(
            status_code=403,
            detail="Alleen een lid of beheerder mag barcodes opslaan.",
        )

    try:
        with engine.begin() as conn:
            return save_gtin_catalog_and_household_link(
                conn,
                household_id=household_context.active_household_id,
                purchase_import_line_id=str(
                    payload.get("purchase_import_line_id") or ""
                ),
                household_article_id=str(
                    payload.get("household_article_id") or ""
                ),
                gtin=gtin,
                article_name=str(
                    payload.get("article_name") or ""
                ),
            )
    except BarcodeHouseholdArticleLinkError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=500,
            detail="De barcode kon niet worden opgeslagen.",
        ) from exc
