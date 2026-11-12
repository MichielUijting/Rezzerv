"""Household-scoped review of historical Catalogus identity conflicts.

The review list follows exact receipt-line -> import-line -> household article
references. The only write action confirms a central retailer/receipt key; it
never changes household articles, receipts, quantities or inventory.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import bindparam, text

from app.db import engine
from app.services.barcode_identity_service import validate_barcode
from app.services.catalog_identity_backfill_preview_service import (
    preview_household_catalog_identity_backfill,
)
from app.services.catalog_identity_confirmation_service import confirm_scanned_retailer_identity
from app.services.catalog_identity_resolution_service import resolve_catalog_identity
from app.services.catalog_retailer_identity_keys import (
    canonical_catalog_retailer, catalog_retailer_aliases,
)
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code, normalize_external_link_receipt_text,
)
from app.services.session_request_context import (
    require_household_admin_from_session, require_platform_permission_from_session,
)

router = APIRouter(prefix="/household-identity-conflicts", tags=["catalog"])


def _authorized_review():
    """Only canonical Frontteam and Superuser sessions may review their own source.

    A Superuser owns the shared *system* household, not any regular household.
    Frontteam can only inspect its own regular household. A household Admin
    without the special Frontteam role must never gain this permission.
    """
    actor = require_platform_permission_from_session("platform.external_products.link_existing")
    household_id = str(actor.active_household_id or "").strip()
    if actor.context_type == "system":
        if not actor.is_platform_superuser or household_id != "0":
            raise HTTPException(403, "Alleen Superuser met Systeemhuishouden heeft toegang")
        return str(actor.user_id), household_id

    if actor.context_type != "regular" or not actor.is_frontteam:
        raise HTTPException(403, "Alleen Frontteam en Superuser mogen historische conflicten beoordelen")

    household_context = require_household_admin_from_session()
    if str(actor.user_id or "") != str(household_context.get("user_id") or ""):
        raise HTTPException(403, "Huishoudcontext en beoordelaar komen niet overeen")
    if household_id != str(household_context.get("active_household_id") or "").strip():
        raise HTTPException(403, "Actief huishouden komt niet overeen met serversessie")
    if not household_id or household_id == "0":
        raise HTTPException(403, "Frontteam vereist een eigen regulier huishouden")
    return str(actor.user_id), household_id


def _identity_key(retailer, description, code):
    result = (
        canonical_catalog_retailer(retailer),
        normalize_external_link_receipt_text(description),
        normalize_external_link_article_code(code),
    )
    if not all(result):
        raise HTTPException(422, "Winkel, bonomschrijving en bonartikelnummer zijn verplicht")
    return result


class ConfirmConflictSourceRequest(BaseModel):
    household_article_id: str
    receipt_line_id: str
    retailer_code: str
    receipt_text: str
    external_article_code: str
    target_gtin: str


@router.get("")
def list_household_catalog_identity_conflicts():
    _actor, household = _authorized_review()
    with engine.connect() as conn:
        if conn.dialect.name != "postgresql":
            raise HTTPException(503, "Historische beoordeling vereist PostgreSQL")
        report = preview_household_catalog_identity_backfill(
            conn, household_id=household, include_conflicts=True,
        )
    return {
        "conflict_count": report["conflict"],
        "source_rows_examined": report["source_rows_examined"],
        "articles_examined": report["articles_examined"],
        "complete": report["conflict_list_complete"],
        "items": report["conflict_items"],
        "products": report["conflict_products"],
        "data_changed": False,
    }


@router.post("/confirm-source")
def confirm_household_catalog_source(request: ConfirmConflictSourceRequest):
    actor, household = _authorized_review()
    retailer, description, number = _identity_key(
        request.retailer_code, request.receipt_text, request.external_article_code,
    )
    checked = validate_barcode(request.target_gtin, "gtin")
    if not checked["valid"]:
        raise HTTPException(422, "Voer een geldige Catalogusbarcode in")
    gtin = checked["normalized_value"]

    with engine.begin() as conn:
        if conn.dialect.name != "postgresql":
            raise HTTPException(503, "Bevestiging vereist PostgreSQL")
        source = conn.execute(text("""
            SELECT rtl.id AS receipt_line_id, ha.global_product_id AS current_product_id,
                   rtl.external_article_code AS code, rtl.barcode AS receipt_gtin,
                   COALESCE(NULLIF(rtl.corrected_raw_label, ''),
                            NULLIF(rtl.normalized_label, ''), rtl.raw_label) AS receipt_text,
                   COALESCE(NULLIF(rt.store_chain, ''), rt.store_name, '') AS retailer
            FROM purchase_import_lines pil
            JOIN purchase_import_batches pib ON pib.id = pil.batch_id
            JOIN receipt_tables rt
              ON rt.id = substr(pib.source_reference, 9)
             AND rt.household_id = pib.household_id
            JOIN receipt_table_lines rtl
              ON rtl.id = substr(pil.external_line_ref, 14)
             AND rtl.receipt_table_id = rt.id
            JOIN household_articles ha
              ON ha.id = pil.matched_household_article_id
             AND ha.household_id = pib.household_id
            WHERE pib.household_id = :household
              AND pib.source_type = 'receipt'
              AND pib.source_reference LIKE 'receipt:%'
              AND pil.external_line_ref LIKE 'receipt-line:%'
              AND ha.id = :article
              AND rtl.id = :receipt_line
              AND rt.deleted_at IS NULL
              AND COALESCE(rtl.is_deleted, FALSE) = FALSE
              AND rtl.line_role = 'product'
              AND CAST(rtl.inventory_eligible AS INTEGER) = 1
            LIMIT 2
            FOR SHARE OF ha, rtl
        """), {
            "household": household,
            "article": request.household_article_id,
            "receipt_line": request.receipt_line_id,
        }).mappings().all()
        if len(source) != 1:
            raise HTTPException(409, "De historische bonbron bestaat niet meer of is niet eenduidig")
        row = source[0]
        if _identity_key(row["retailer"], row["receipt_text"], row["code"]) != (
            retailer, description, number,
        ):
            raise HTTPException(409, "De bonbron is gewijzigd. Laad de beoordeling opnieuw.")
        scanned = str(row.get("receipt_gtin") or "").strip()
        if scanned:
            receipt_gtin = validate_barcode(scanned, "gtin")
            if receipt_gtin["valid"] and receipt_gtin["normalized_value"] != gtin:
                raise HTTPException(409, "De originele bonbarcode wijkt af van de gekozen Catalogusbarcode")

        match = resolve_catalog_identity(conn, gtin=gtin)
        if match["status"] != "matched":
            raise HTTPException(409, "De gekozen barcode heeft geen uniek actief Catalogusproduct")
        product_id = match["global_product_id"]
        current = str(row.get("current_product_id") or "").strip()
        if current and current != product_id:
            raise HTTPException(409, "Dit huishoudartikel is aan een ander Catalogusproduct gekoppeld; eerst afzonderlijk beoordelen")

        # Legacy code-only links have no proven description. Do not promote
        # them silently or reinterpret them as a complete receipt identity.
        legacy = conn.execute(text("""
            SELECT 1 FROM external_article_product_links
            WHERE retailer_code IN :retailers
              AND external_article_code = :code
              AND COALESCE(receipt_text_normalized, '') = ''
              AND status IN ('confirmed', 'classification_pending')
            LIMIT 1
        """).bindparams(
            bindparam("retailers", expanding=True)
        ), {"retailers": catalog_retailer_aliases(retailer), "code": number}).first()
        if legacy:
            raise HTTPException(409, "Oude winkelcode zonder bonomschrijving moet eerst apart worden onderzocht")
        try:
            result = confirm_scanned_retailer_identity(
                conn, retailer_code=retailer, receipt_text=description,
                external_article_code=number, scanned_gtin=gtin, confirmed_by=actor,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if result["global_product_id"] != product_id:
            raise HTTPException(409, "Bevestigde Catalogusidentiteit wijkt af")
        return {
            "status": result["status"],
            "changed": bool(result["changes"]),
            "global_product_id": product_id,
            "household_article_changes": 0,
            "stock_changes": 0,
            "receipt_changes": 0,
        }
