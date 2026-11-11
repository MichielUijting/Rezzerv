from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Header, HTTPException
from sqlalchemy import text

from app.db import engine
from app.services.catalog_identity_confirmation_service import confirm_scanned_retailer_identity
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
    """Confirm a store code using an actual receipt line in the actor's household.

    The caller never supplies a trusted household ID. A scanned barcode is
    required, and the supplied retailer+code must belong to the exact
    household article via the canonical receipt import lineage.
    """
    runtime_context = _require_auth(authorization)
    household_context = household_context_from_runtime_context(runtime_context)
    if household_context.role == "viewer":
        raise HTTPException(status_code=403, detail="Alleen een lid of beheerder mag artikelen koppelen.")
    household = str(household_context.active_household_id or "").strip()
    article_id = str(payload.get("household_article_id") or "").strip()
    retailer = normalize_external_link_retailer_code(payload.get("retailer_code"))
    code = normalize_external_link_article_code(payload.get("external_article_code"))
    gtin = str(payload.get("gtin") or "").strip()
    if not household or not article_id or not retailer or not code or not gtin:
        raise HTTPException(status_code=422, detail="Huishoudartikel, winkel, artikelcode en barcode zijn verplicht")
    try:
        with engine.begin() as conn:
            existing_article = conn.execute(text("""
                SELECT id FROM household_articles
                WHERE id = :article AND household_id = :household
            """), {"article": article_id, "household": household}).first()
            if existing_article is None:
                raise HTTPException(status_code=404, detail="Huishoudartikel is niet gevonden")
            sources = conn.execute(text("""
                SELECT COALESCE(NULLIF(rt.store_chain, ''), rt.store_name, '') AS retailer,
                       rtl.external_article_code AS article_code
                FROM purchase_import_lines pil
                JOIN purchase_import_batches pib ON pib.id = pil.batch_id
                JOIN receipt_tables rt
                  ON rt.id = substr(pib.source_reference, 9)
                 AND rt.household_id = pib.household_id
                JOIN receipt_table_lines rtl
                  ON rtl.id = substr(pil.external_line_ref, 14)
                 AND rtl.receipt_table_id = rt.id
                WHERE pib.household_id = :household
                  AND pib.source_type = 'receipt'
                  AND pib.source_reference LIKE 'receipt:%'
                  AND pil.external_line_ref LIKE 'receipt-line:%'
                  AND pil.matched_household_article_id = :article
                  AND COALESCE(rtl.is_deleted, FALSE) = FALSE
            """), {"household": household, "article": article_id}).mappings().all()
            if not any(
                normalize_external_link_retailer_code(row["retailer"]) == retailer
                and normalize_external_link_article_code(row["article_code"]) == code
                for row in sources
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Deze winkelartikelcode is niet aantoonbaar gekoppeld aan dit huishoudartikel",
                )
            return confirm_scanned_retailer_identity(
                conn, retailer_code=retailer, external_article_code=code,
                scanned_gtin=gtin,
                confirmed_by=str(runtime_context.get("user_id") or runtime_context.get("username") or "").strip(),
            )
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
