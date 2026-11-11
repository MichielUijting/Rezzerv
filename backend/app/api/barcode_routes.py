from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Header, HTTPException
from sqlalchemy import text

from app.db import engine
from app.services.catalog_identity_confirmation_service import confirm_scanned_retailer_identity
from app.services.catalog_identity_live_repair_service import repair_household_articles_for_confirmed_store_code
from app.services.session_request_context import require_platform_permission_from_session
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code, normalize_external_link_retailer_code,
)
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


@router.post("/confirm-retailer-code")
def confirm_retailer_code_from_barcode(
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: Optional[str] = Header(None),
):
    """Confirm an existing Catalogus GTIN for a real receipt line.

    No caller-supplied household or product ID is trusted. Only a receipt
    line that belongs to the current authenticated household may authorize
    a retailer-code identity. This action never modifies household stock.
    """
    runtime_context = _require_auth(authorization)
    require_platform_permission_from_session("platform.external_products.link_existing")
    household_context = household_context_from_runtime_context(runtime_context)
    if household_context.role == "viewer":
        raise HTTPException(status_code=403, detail="Alleen een lid of beheerder mag artikelen koppelen.")
    household = str(household_context.active_household_id or "").strip()
    receipt_item_id = str(payload.get("receipt_item_id") or "").strip()
    retailer = normalize_external_link_retailer_code(payload.get("retailer_code"))
    code = normalize_external_link_article_code(payload.get("external_article_code"))
    gtin = str(payload.get("gtin") or "").strip()
    if not household or not receipt_item_id or not retailer or not code or not gtin:
        raise HTTPException(status_code=422, detail="Bonregel, winkel, artikelcode en barcode zijn verplicht")
    if not receipt_item_id.startswith("receipt-table-line:"):
        raise HTTPException(status_code=422, detail="Bevestiging vereist een originele kassabonregel")
    receipt_line_id = receipt_item_id[len("receipt-table-line:"):]
    if not receipt_line_id:
        raise HTTPException(status_code=422, detail="Kassabonregel ontbreekt")
    try:
        with engine.begin() as conn:
            source = conn.execute(text("""
                SELECT COALESCE(NULLIF(rt.store_chain, ''), rt.store_name, '') AS retailer,
                       rtl.external_article_code AS article_code
                FROM receipt_table_lines rtl
                JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
                WHERE rtl.id = :line AND rt.household_id = :household
                  AND COALESCE(rtl.is_deleted, FALSE) = FALSE
                  AND rt.deleted_at IS NULL
                  AND rtl.line_role = 'product'
                  AND CAST(rtl.inventory_eligible AS INTEGER) = 1
            """), {"household": household, "line": receipt_line_id}).mappings().first()
            if source is None:
                raise HTTPException(status_code=404, detail="Originele bonregel is niet beschikbaar in dit huishouden")
            if (normalize_external_link_retailer_code(source["retailer"]) != retailer
                or normalize_external_link_article_code(source["article_code"]) != code):
                raise HTTPException(
                    status_code=409,
                    detail="De winkelartikelcode komt niet overeen met de originele bonregel",
                )
            actor = str(runtime_context.get("user_id") or runtime_context.get("email") or "").strip()
            confirmed = confirm_scanned_retailer_identity(
                conn, retailer_code=retailer, external_article_code=code,
                scanned_gtin=gtin, confirmed_by=actor,
            )
            # Historical repair is a separate savepoint: a verified central
            # identity must survive even when an old receipt is inconsistent.
            try:
                with conn.begin_nested():
                    repair = repair_household_articles_for_confirmed_store_code(
                        conn, household_id=household, retailer_code=retailer,
                        external_article_code=code,
                        global_product_id=confirmed["global_product_id"],
                    )
            except Exception:
                # The savepoint rolls back *every* attempted historical write;
                # the response must not pretend the historical repair worked.
                import logging
                logging.getLogger(__name__).exception(
                    "Historical household identity repair deferred after confirmation"
                )
                repair = {"updated": 0, "status": "deferred"}
            return {**confirmed, "historical_repair": repair}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
