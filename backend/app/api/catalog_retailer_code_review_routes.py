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
from app.services.session_request_context import require_platform_permission_from_session
from app.services.external_article_product_link_service import (
    normalize_external_link_retailer_code,
    normalize_external_link_article_code,
    normalize_external_link_receipt_text,
)

router = APIRouter(prefix="/{global_product_id}/retailer-codes", tags=["catalog"])

def _permission():
    return require_platform_permission_from_session("platform.external_products.link_existing")

def _key(retailer, description, article_number):
    key = (
        normalize_external_link_retailer_code(retailer),
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
    if request.expected_product_id != global_product_id:
        raise HTTPException(409, "Catalogusproduct is tussentijds gewijzigd")
    with engine.begin() as conn:
        if conn.dialect.name != "postgresql":
            raise HTTPException(503, "Beoordelen vereist PostgreSQL")
        # Serialize all edits affecting a retailer/code, including concurrent reviews.
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 675))"),
                     {"key":retailer+"|"+article_number})
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
            WHERE retailer_code=:retailer AND receipt_text_normalized=:description
              AND external_article_code=:article AND status='confirmed'
            FOR UPDATE
        """), {"retailer":retailer,"description":description,"article":article_number}).mappings().all()
        if any(str(x["global_product_id"]) != global_product_id for x in triples):
            raise HTTPException(409, "Deze winkel, omschrijving en bonartikelnummer zijn al aan een ander product gekoppeld")
        if len(triples) > 1:
            raise HTTPException(409, "Meerdere bevestigde koppelingen voor dezelfde combinatie; eerst bronconflict onderzoeken")
        # The existing resolver also searches by retailer+code without text. Until
        # it understands the complete PO key, never create a code-only ambiguity.
        code_owners = conn.execute(text("""
            SELECT DISTINCT global_product_id FROM external_article_product_links
            WHERE retailer_code=:retailer AND external_article_code=:article
              AND status='confirmed'
        """), {"retailer":retailer,"article":article_number}).scalars().all()
        if any(str(x)!=global_product_id for x in code_owners):
            raise HTTPException(409, "Deze winkelcode heeft elders een andere bevestigde productidentiteit; eerst resolver aanpassen")
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
        # A single retailer+article number still drives existing receipt resolution.
        # Correct only when exactly this one active code row exists; never risk
        # creating a code-only ambiguity or silently changing other descriptions.
        code_rows = conn.execute(text("""
            SELECT id FROM external_article_product_links
            WHERE retailer_code=:retailer AND external_article_code=:article
              AND status IN ('confirmed','classification_pending')
            FOR UPDATE
        """), {"retailer":retailer,"article":article_number}).scalars().all()
        if {str(v) for v in code_rows} != {str(request.link_id)}:
            raise HTTPException(409, "Dezelfde winkelcode komt bij meerdere omschrijvingen voor; correctie vereist eerst een uitgebreidere herkenningsregel")
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
