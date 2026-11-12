"""Review and deliberate correction of retailer receipt identities in Catalogus.

PO contract: the store + normalized receipt description + receipt article number
has no more than one confirmed Catalogus product/GTIN. One description may have
many receipt numbers. Never infer a household-article merge from this relation.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.db import engine
from app.services.catalog_identity_confirmation_service import confirm_scanned_retailer_identity
from app.services.session_request_context import require_platform_permission_from_session
from app.services.catalog_retailer_identity_keys import canonical_catalog_retailer, catalog_retailer_aliases
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code,
    normalize_external_link_receipt_text,
)

router = APIRouter(prefix="/{global_product_id}/retailer-codes", tags=["catalog"])

def _permission():
    return require_platform_permission_from_session("platform.external_products.link_existing")

def _key(retailer, description, article_number):
    key = (
        canonical_catalog_retailer(retailer),
        normalize_external_link_receipt_text(description),
        normalize_external_link_article_code(article_number),
    )
    if not all(key):
        raise HTTPException(422, "Winkel, bonomschrijving en bonartikelnummer zijn alle drie verplicht")
    return key

class ReviewRequest(BaseModel):
    link_id: str
    expected_product_id: str
    retailer_code: str
    receipt_text: str
    external_article_code: str
    action: str
    target_gtin: str | None = None


class AddRetailerCodeRequest(BaseModel):
    retailer_code: str
    receipt_text: str
    external_article_code: str
    expected_gtin: str


@router.post("/add")
def add_catalog_retailer_code(global_product_id: str, request: AddRetailerCodeRequest):
    context = _permission()
    actor = str(context.user_id or "").strip()
    if not actor:
        raise HTTPException(403, "Geen bevestigde gebruiker beschikbaar")
    retailer, description, number = _key(
        request.retailer_code, request.receipt_text, request.external_article_code
    )
    with engine.begin() as conn:
        if conn.dialect.name != "postgresql":
            raise HTTPException(503, "Winkelcodebevestiging vereist PostgreSQL")
        product = conn.execute(text("""
            SELECT id, primary_gtin FROM global_products
            WHERE id=:id AND LOWER(COALESCE(status,'active'))='active'
            FOR UPDATE
        """), {"id":global_product_id}).mappings().first()
        if not product:
            raise HTTPException(404, "Catalogusproduct niet gevonden")
        gtin = str(product["primary_gtin"] or "").strip()
        if not gtin or gtin != request.expected_gtin:
            raise HTTPException(409, "De barcode van het Catalogusproduct is gewijzigd of ontbreekt")
        # A platform editor may only confirm a real receipt combination, not
        # invent a source identity from a typed description.
        evidence = conn.execute(text("""
            SELECT COALESCE(NULLIF(rt.store_chain,''), rt.store_name,'') AS retailer,
                   COALESCE(NULLIF(rtl.corrected_raw_label,''),
                            NULLIF(rtl.normalized_label,''),rtl.raw_label) AS receipt_text
            FROM receipt_table_lines rtl
            JOIN receipt_tables rt ON rt.id=rtl.receipt_table_id
            WHERE rtl.external_article_code=:article_number
              AND COALESCE(rtl.is_deleted,FALSE)=FALSE
              AND rt.deleted_at IS NULL
              AND rtl.line_role='product'
              AND CAST(rtl.inventory_eligible AS INTEGER)=1
            LIMIT 2000
        """), {"article_number":number}).mappings().all()
        if not any(
            source.get("retailer") and source.get("receipt_text")
            and _key(source["retailer"], source["receipt_text"], number)
              == (retailer, description, number)
            for source in evidence
        ):
            raise HTTPException(409, "Deze combinatie is niet op een bestaande kassabon aangetroffen")
        legacy = conn.execute(text("""
            SELECT id FROM external_article_product_links
            WHERE retailer_code = ANY(:aliases) AND external_article_code=:number
              AND COALESCE(receipt_text_normalized,'')=''
              AND status IN ('confirmed','classification_pending')
            LIMIT 1
        """), {"aliases":list(catalog_retailer_aliases(retailer)),
               "number":number}).first()
        if legacy:
            raise HTTPException(409, "Deze winkelcode heeft een oude koppeling zonder bonomschrijving; eerst afzonderlijk beoordelen")
        try:
            saved = confirm_scanned_retailer_identity(
                conn, retailer_code=retailer, receipt_text=description,
                external_article_code=number, scanned_gtin=gtin, confirmed_by=actor,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if saved["global_product_id"] != global_product_id:
            raise HTTPException(409, "Bevestigde barcode hoort niet bij dit Catalogusproduct")
        return {"status":saved["status"], "global_product_id":global_product_id,
                "receipt_text":description, "external_article_code":number,
                "changed":bool(saved["changes"])}


@router.get("")
def list_catalog_retailer_codes(global_product_id: str):
    _permission()
    with engine.connect() as conn:
        product = conn.execute(text(
            "SELECT id, name, primary_gtin FROM global_products WHERE id=:id AND LOWER(COALESCE(status,'active'))='active'"
        ), {"id":global_product_id}).mappings().first()
        if not product:
            raise HTTPException(404, "Catalogusproduct niet gevonden")
        rows = conn.execute(text("""
            SELECT l.id, l.retailer_code, l.receipt_text_normalized,
                   l.external_article_code, l.global_product_id, l.status,
                   l.confirmed_by, l.confirmed_at,
                   gp.name AS product_name, gp.primary_gtin
            FROM external_article_product_links l
            JOIN global_products gp ON gp.id=l.global_product_id
            WHERE l.global_product_id=:id AND l.status IN ('confirmed','classification_pending')
            ORDER BY l.retailer_code, l.receipt_text_normalized, l.external_article_code, l.id
        """), {"id":global_product_id}).mappings().all()
        return {"product":dict(product), "items":[dict(r) for r in rows]}

@router.post("/review")
def review_catalog_retailer_code(global_product_id: str, request: ReviewRequest):
    context = _permission()
    actor = str(context.user_id or "").strip()
    if not actor:
        raise HTTPException(403, "Geen bevestigde gebruiker beschikbaar")
    if request.action not in ("confirm","correct"):
        raise HTTPException(422, "Kies Bevestigen of Corrigeren")
    retailer, description, article_number = _key(
        request.retailer_code,request.receipt_text,request.external_article_code)
    aliases = list(catalog_retailer_aliases(retailer))
    if request.expected_product_id != global_product_id:
        raise HTTPException(409, "Catalogusproduct is tussentijds gewijzigd")
    with engine.begin() as conn:
        if conn.dialect.name != "postgresql":
            raise HTTPException(503, "Beoordelen vereist PostgreSQL")
        # Serialize all edits affecting a retailer/code, including concurrent reviews.
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 672))"),
                     {"key":"|".join((retailer,description,article_number))})
        row = conn.execute(text("""
            SELECT id, global_product_id, status, retailer_code, receipt_text_normalized,
                   external_article_code
            FROM external_article_product_links
            WHERE id=:id FOR UPDATE
        """), {"id":request.link_id}).mappings().first()
        if not row or row["status"] not in ("confirmed","classification_pending"):
            raise HTTPException(409, "De winkelcodekoppeling bestaat niet meer of is gewijzigd")
        if (str(row["global_product_id"]) != global_product_id or
            _key(row["retailer_code"],row["receipt_text_normalized"],
                 row["external_article_code"]) != (retailer,description,article_number)):
            raise HTTPException(409, "De brongegevens zijn gewijzigd. Laad het product opnieuw.")
        # Unique *triple* is the PO authority. Never silently overwrite competitors.
        triples = conn.execute(text("""
            SELECT id, global_product_id FROM external_article_product_links
            WHERE retailer_code = ANY(:retailer_aliases) AND receipt_text_normalized=:description
              AND external_article_code=:article AND status IN ('confirmed','classification_pending')
            FOR UPDATE
        """), {"retailer_aliases":aliases,"description":description,"article":article_number}).mappings().all()
        if any(str(x["global_product_id"]) != global_product_id for x in triples):
            raise HTTPException(409, "Deze winkel, omschrijving en bonartikelnummer zijn al aan een ander product gekoppeld")
        if len(triples) > 1:
            raise HTTPException(409, "Meerdere bevestigde koppelingen voor dezelfde combinatie; eerst bronconflict onderzoeken")
        # Different descriptions may legitimately reuse a number. The
        # updated resolver uses the complete key and fails closed when a
        # legacy caller can provide only an ambiguous retailer/code.
        if request.action=="confirm":
            if row["status"] != "confirmed":
                raise HTTPException(409, "Classificatie-in-afwachting moet eerst via bestaande bevestiging worden afgerond")
            changed = conn.execute(text("""
                UPDATE external_article_product_links
                SET confirmed_by=:actor,
                    confirmed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id=:id AND global_product_id=:product AND status='confirmed'
            """), {"id":request.link_id,"product":global_product_id,"actor":actor})
            if changed.rowcount != 1:
                raise HTTPException(409, "Bevestiging kon niet veilig worden opgeslagen")
            return {"status":"confirmed","changed":True,"global_product_id":global_product_id}
        # No automatic reassignment of historical receipt, household or stock records.
        # Require confirmed active target GTIN, check-code ownership and source review.
        gtin = str(request.target_gtin or "").strip()
        if not gtin or not gtin.isdigit():
            raise HTTPException(422, "Voer de bevestigde barcode van het juiste Catalogusproduct in")
        target = conn.execute(text("""
            SELECT id, name, primary_gtin FROM global_products
            WHERE primary_gtin=:gtin AND LOWER(COALESCE(status,'active'))='active'
        """), {"gtin":gtin}).mappings().all()
        if len(target) != 1:
            raise HTTPException(409, "Barcode verwijst niet eenduidig naar een actief Catalogusproduct")
        target_id = str(target[0]["id"])
        if target_id == global_product_id:
            raise HTTPException(409, "De barcode hoort al bij dit Catalogusproduct")
        # Correct this complete PO key only; other descriptions and codes
        # are independent and must remain untouched.
        # The old product may already be bound to household stock. Never repoint
        # a retailer identity that would contradict a linked household article.
        existing_household = conn.execute(text("""
            SELECT id FROM household_articles
            WHERE global_product_id=:old_product LIMIT 1
        """), {"old_product":global_product_id}).first()
        if existing_household:
            raise HTTPException(409, "Er zijn huishoudartikelen gekoppeld aan de huidige productidentiteit. Eerst afzonderlijk beoordelen; voorraad blijft behouden.")
        if row["status"] != "confirmed":
            raise HTTPException(409, "Een voorlopige koppeling moet via de bestaande bevestigingsprocedure worden afgerond.")
        updated = conn.execute(text("""
            UPDATE external_article_product_links SET
                global_product_id=:target,
                confirmed_by=:actor,
                confirmed_at=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:id AND global_product_id=:expected
              AND status='confirmed'
        """), {"target":target_id,"id":request.link_id,"expected":global_product_id,"actor":actor})
        if updated.rowcount != 1:
            raise HTTPException(409, "Koppeling is tussentijds gewijzigd; correctie geannuleerd.")
        return {"status":"corrected","changed":True,
                "previous_product_id":global_product_id,"global_product_id":target_id}
