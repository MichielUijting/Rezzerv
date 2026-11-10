"""Superuser-only, explicitly reviewed import of spreadsheet barcode proposals.

CSV preview is read-only. Each accepted row is resolved again against the
central receipt-article identity and written through the existing ED2 service.
Never replace a confirmed barcode, use a fuzzy match or change household stock.
"""
from __future__ import annotations

import csv
import io
from collections import Counter
from typing import Any
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from app.api.catalog_routes import save_ed2_manual_barcode, Ed2ManualBarcodeRequest
from app.services.external_unlinked_articles_service import (
    list_all_external_articles, _overview_retailer_code,
)
from app.services.external_article_product_link_service import (
    normalize_external_link_receipt_text,
    normalize_external_link_article_code,
)
from app.services.barcode_identity_service import validate_barcode, calculate_gtin_check_digit
from app.services.session_request_context import resolve_current_server_session
from app.services.off_search_service import lookup_off_product_by_gtin

router = APIRouter(prefix="/api/catalog/ed2/barcode-import", tags=["catalog"])
HEADERS = ("Artikel", "Winkelketen", "Bonartikelnummer", "Art./Barcode")
MAX_BYTES = 2_000_000
MAX_ROWS = 3000
MAX_OFF_NAMES = 10


class PreviewRequest(BaseModel):
    csv_text: str


class OffNamesRequest(BaseModel):
    gtins: list[str]


class ApproveRequest(BaseModel):
    receipt_item_id: str
    retailer: str
    article: str
    article_number: str
    gtin: str
    allow_off_mismatch: bool = False


def _require_superuser() -> None:
    context = resolve_current_server_session()
    if not context.is_platform_superuser:
        raise HTTPException(status_code=403, detail="Alleen de Superuser mag barcodes importeren.")


def _key(retailer: Any, article: Any, number: Any) -> tuple[str, str, str]:
    return (
        _overview_retailer_code(retailer),
        normalize_external_link_receipt_text(article),
        normalize_external_link_article_code(number),
    )


def _is_derived_receipt_barcode(article_number: Any, barcode: Any) -> bool:
    """A calculated receipt identifier is not evidence of an assigned GTIN."""
    number = str(article_number or "").strip()
    value = str(barcode or "").strip()
    if not number.isascii() or not number.isdigit() or not (1 <= len(number) <= 7):
        return False
    body = "2" + number.zfill(7) + "0000"
    return value == body + str(calculate_gtin_check_digit(body))


def _live_index() -> dict[tuple[str, str, str], list[dict]]:
    index: dict[tuple[str, str, str], list[dict]] = {}
    for item in list_all_external_articles().get("items", []):
        key = _key(item.get("retailer_code"), item.get("receipt_line_text"),
                   item.get("receipt_article_number"))
        index.setdefault(key, []).append(item)
    return index


@router.post("/preview")
def preview_barcode_import(payload: PreviewRequest):
    _require_superuser()
    raw = payload.csv_text.lstrip("\ufeff")
    if not raw or len(raw.encode("utf-8")) > MAX_BYTES or "\x00" in raw:
        raise HTTPException(status_code=422, detail="CSV ontbreekt, is te groot of is ongeldig.")
    try:
        reader = csv.DictReader(io.StringIO(raw, newline=""), delimiter=";", strict=True)
        if not reader.fieldnames:
            raise ValueError("Het CSV-bestand heeft geen kolomkoppen.")
        # Four-column exports are accepted for preview; enhanced CSV may
        # additionally carry verified provenance in Aanvulstatus.
        missing = [column for column in HEADERS if column not in reader.fieldnames]
        if missing:
            raise ValueError("De volgende kolommen ontbreken: " + ", ".join(missing) + ".")
        source_rows = list(reader)
    except (csv.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"CSV kon niet worden gelezen: {exc}") from exc
    if len(source_rows) > MAX_ROWS:
        raise HTTPException(status_code=422, detail="Maximaal 3000 artikelregels per import.")
    index = _live_index()
    seen: set[tuple[str, str, str]] = set()
    results: list[dict] = []
    skipped = 0
    for line, row in enumerate(source_rows, start=2):
        if None in row:
            raise HTTPException(status_code=422, detail=f"Extra kolommen op regel {line}.")
        barcode = str(row.get("Art./Barcode") or "").strip()
        if not barcode and "Aanvulstatus" not in reader.fieldnames:
            skipped += 1
            continue
        # Keep explicit provenance filtering for enhanced spreadsheets.
        if "Aanvulstatus" in reader.fieldnames and (
            (row.get("Aanvulstatus") or "").strip().lower() != "aangevuld: officieel artikelnummer"
        ):
            skipped += 1
            continue
        key = _key(row.get("Winkelketen"), row.get("Artikel"), row.get("Bonartikelnummer"))
        validation = validate_barcode(barcode, "gtin")
        current = index.get(key, [])
        status = "klaar"
        reason = ""
        if not key[0] or not key[1] or not key[2]:
            status, reason = "geblokkeerd", "Winkel, artikelnaam of bonartikelnummer ontbreekt."
        elif key in seen:
            status, reason = "geblokkeerd", "Dubbele artikelregel in het importbestand."
        elif not validation["valid"]:
            status, reason = "geblokkeerd", "Barcode heeft geen geldige GTIN-controle."
        elif _is_derived_receipt_barcode(row.get("Bonartikelnummer"), barcode):
            status, reason = (
                "geblokkeerd",
                "Afgeleide code uit het bonartikelnummer; geen aangetoonde productbarcode.",
            )
        elif len(current) != 1:
            status, reason = "geblokkeerd", "Geen unieke overeenkomst in Artikelbeheer."
        elif current[0].get("link_status") != "unlinked" or current[0].get("article_code") or current[0].get("manual_barcode"):
            existing = current[0]
            catalog_gtin = str(existing.get("article_code") or "").strip()
            manual_gtin = str(existing.get("manual_barcode") or "").strip()
            proposed = validation["normalized_value"]
            if (catalog_gtin and manual_gtin and catalog_gtin != manual_gtin):
                status, reason = "conflict", "Barcodeconflict: Catalogus en handmatige barcode verschillen"
            elif (catalog_gtin and catalog_gtin == proposed) or (
                not catalog_gtin and manual_gtin == proposed
            ):
                status, reason = "al_gekoppeld", "Al gekoppeld – barcode komt overeen"
                if existing.get("link_status") == "classification_pending":
                    reason += " (classificatie ontbreekt)"
            elif (catalog_gtin and catalog_gtin != proposed) or (manual_gtin and manual_gtin != proposed):
                status, reason = "conflict", "Barcodeconflict: bestaande barcode wijkt af"
            else:
                status, reason = "geblokkeerd", "Cataloguskoppeling bestaat zonder zichtbare barcode"
        seen.add(key)
        existing = current[0] if len(current) == 1 else {}
        results.append({
            "line": line, "article": row.get("Artikel") or "",
            "retailer": row.get("Winkelketen") or "",
            "article_number": row.get("Bonartikelnummer") or "",
            "gtin": validation["normalized_value"] if validation["valid"] else barcode,
            "source": row.get("Bron/onderbouwing") or "",
            "product_name": row.get("Gevonden productnaam") or "",
            "receipt_item_id": str(current[0].get("id")) if len(current) == 1 else "",
            "status": status, "reason": reason,
            "existing_catalog_gtin": str(existing.get("article_code") or ""),
            "existing_manual_gtin": str(existing.get("manual_barcode") or ""),
            "existing_catalog_product": str(existing.get("catalog_product_name") or ""),
            "existing_link_status": str(existing.get("link_status") or ""),
            "has_barcode_conflict": bool(
                existing.get("article_code") and existing.get("manual_barcode")
                and existing.get("article_code") != existing.get("manual_barcode")
            ) or status == "conflict",
        })
    return {
        "items": results, "skipped": skipped,
        "ready": sum(item["status"] == "klaar" for item in results),
        "blocked": sum(item["status"] != "klaar" for item in results),
        "total": len(source_rows),
    }


def _off_name_lookup(gtin: str) -> dict:
    """Exact GTIN lookup, never a fuzzy product suggestion or catalog write."""
    try:
        result = lookup_off_product_by_gtin(gtin)
    except Exception:
        return {"gtin": gtin, "status": "unavailable", "product_name": "", "brand": "", "quantity": ""}
    product = result.get("product") or {}
    status = result.get("status")
    if status == "found" and str(product.get("product_name") or "").strip():
        return {
            "gtin": gtin, "status": "found",
            "product_name": str(product["product_name"]).strip(),
            "brand": str(product.get("brand") or "").strip(),
            "quantity": str(product.get("quantity") or "").strip(),
        }
    return {
        "gtin": gtin,
        "status": "unavailable" if status == "external_source_unavailable" else (
            "no_name" if status == "found" else "not_found"
        ),
        "product_name": "", "brand": "", "quantity": "",
    }


@router.post("/off-names")
def lookup_barcode_import_off_names(payload: OffNamesRequest):
    """Read-only enrichment for the visible import page; never writes to InHuis."""
    _require_superuser()
    if not payload.gtins or len(payload.gtins) > MAX_OFF_NAMES:
        raise HTTPException(status_code=422, detail="Maximaal 10 barcodes per OFF-controle.")
    normalized = []
    for raw in payload.gtins:
        validation = validate_barcode(raw, "gtin")
        if not validation["valid"]:
            raise HTTPException(status_code=422, detail="Ongeldige barcode voor OFF-controle.")
        gtin = validation["normalized_value"]
        if gtin not in normalized:
            normalized.append(gtin)
    # Bounded requests: one page, maximum three simultaneous OFF lookups.
    with ThreadPoolExecutor(max_workers=3) as pool:
        items = list(pool.map(_off_name_lookup, normalized))
    return {"items": items, "mutated": False}


@router.post("/approve")
def approve_barcode_import(payload: ApproveRequest):
    _require_superuser()
    validation = validate_barcode(payload.gtin, "gtin")
    if not validation["valid"]:
        raise HTTPException(status_code=422, detail="Ongeldige barcode.")
    if _is_derived_receipt_barcode(payload.article_number, validation["normalized_value"]):
        raise HTTPException(
            status_code=422,
            detail="Afgeleide code uit het bonartikelnummer is geen aangetoonde productbarcode.",
        )
    matches = _live_index().get(_key(payload.retailer, payload.article, payload.article_number), [])
    if len(matches) != 1 or str(matches[0].get("id")) != payload.receipt_item_id:
        raise HTTPException(status_code=409, detail="Artikelidentiteit is gewijzigd. Importeer het bestand opnieuw.")
    item = matches[0]
    if item.get("link_status") != "unlinked" or item.get("article_code") or item.get("manual_barcode"):
        raise HTTPException(status_code=409, detail="Artikel is intussen gekoppeld of heeft al een barcode.")
    return save_ed2_manual_barcode(
        Ed2ManualBarcodeRequest(receipt_item_id=payload.receipt_item_id,
                                gtin=validation["normalized_value"],
                                allow_off_mismatch=payload.allow_off_mismatch,
                                import_off_product_override=payload.allow_off_mismatch)
    )
