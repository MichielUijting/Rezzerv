"""CBS classification API, independent of GS1 and Shopify authorities.

Only authenticated platform Superusers and Frontteam with canonical privileges
may confirm or remove classifications; clients never supply role or actor IDs.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text as __sql

from app.db import engine
from app.services.cbs_classification_service import (
    CBSConcurrentChange,
    CBSDecisionError,
    confirm_cbs_batch,
    remove_cbs_batch,
    search_verified_categories,
    browse_verified_categories,
    suggest_verified_categories,
)
from app.services.article_workqueue_service import (
    load_classification_workqueue, load_identification_workqueue,
)
from app.services.session_request_context import require_platform_permission_from_session

router = APIRouter(prefix="/api/cbs-classifications", tags=["cbs-classification"])


def _actor(permission: str):
    context = require_platform_permission_from_session(permission)
    if not (context.is_platform_superuser or context.is_frontteam):
        raise HTTPException(status_code=403, detail="Alleen Superusers en Frontteamleden mogen artikelclassificaties beheren.")
    if context.is_platform_superuser and context.context_type != "system":
        raise HTTPException(status_code=403, detail="Systeemcontext vereist.")
    if context.is_frontteam and not context.is_platform_superuser and context.context_type != "regular":
        raise HTTPException(status_code=403, detail="Reguliere Frontteamcontext vereist.")
    return context


class Confirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    global_product_id: str = Field(min_length=1, max_length=200)
    expected_product_name: str = Field(min_length=1, max_length=500)
    cbs_code: str = Field(pattern=r"^[0-9]{6}$")
    reference_version: str = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=0)


class ConfirmationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selections: list[Confirmation] = Field(min_length=1, max_length=100)


class Removal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    global_product_id: str = Field(min_length=1, max_length=200)
    expected_product_name: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)


class RemovalBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selections: list[Removal] = Field(min_length=1, max_length=100)


@router.get("/identification-workqueue")
def identification_workqueue():
    """Deduplicated unresolved retailer/receipt identities, never household stock."""
    _actor("platform.external_products.view")
    with engine.connect() as conn:
        return load_identification_workqueue(conn)


@router.get("/workqueue")
def classification_workqueue(offset: int = Query(default=0, ge=0),
                             limit: int = Query(default=100, ge=1, le=100)):
    """Canonical per-product, per-system read-only work queue."""
    _actor("platform.external_products.view")
    with engine.connect() as conn:
        return load_classification_workqueue(conn, offset=offset, limit=limit)


@router.get("/products")
def products(offset: int = Query(default=0, ge=0),
             limit: int = Query(default=100, ge=1, le=100)):
    """List central Catalogus products, including ones without barcode."""
    _actor("platform.external_products.view")
    with engine.connect() as conn:
        total = int(conn.execute(__sql("""
            SELECT COUNT(*) FROM global_products
            WHERE LOWER(COALESCE(status, '')) <> 'deleted'
        """)).scalar_one())
        rows = conn.execute(__sql("""
            SELECT gp.id, gp.name, gp.brand, gp.primary_gtin,
                   cc.cbs_code, cc.reference_version, cc.version, cc.is_active,
                   ref.name_nl AS category_name, ref.level AS category_level
            FROM global_products gp
            LEFT JOIN global_product_cbs_classifications cc
                   ON cc.global_product_id = gp.id
            LEFT JOIN cbs_ecoicop_categories ref
                   ON ref.cbs_code = cc.cbs_code AND ref.reference_version = cc.reference_version
            WHERE LOWER(COALESCE(gp.status, '')) <> 'deleted'
            ORDER BY LOWER(gp.name), gp.id
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset}).mappings().all()
    return {"items": [
        {"id": str(row["id"]), "name": str(row["name"] or ""),
         "brand": str(row["brand"] or ""),
         "gtin": str(row["primary_gtin"] or ""),
         "cbs_code": str(row["cbs_code"] or "") if row["is_active"] else "",
         "category_name": str(row["category_name"] or "") if row["is_active"] else "",
         "category_level": row["category_level"] if row["is_active"] else None,
         "reference_version": str(row["reference_version"] or "") if row["is_active"] else "",
         "version": int(row["version"] or 0),
         "classified": bool(row["is_active"])}
        for row in rows
    ], "total": total}


@router.get("/categories")
def categories(query: str = Query(min_length=2, max_length=100), limit: int = Query(default=40, ge=1, le=50)):
    _actor("platform.external_products.view")
    with engine.connect() as conn:
        items = search_verified_categories(conn, query, limit=limit)
    return {"items": items, "total": len(items), "verified_only": True}


@router.get("/categories/browse")
def browse_categories(parent_code: str | None = Query(default=None, pattern=r"^[0-9]{6}$")):
    _actor("platform.external_products.view")
    try:
        with engine.connect() as conn:
            items = browse_verified_categories(conn, parent_code)
        return {"items": items, "total": len(items), "verified_only": True}
    except CBSDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/categories/suggest")
def suggest_categories(query: str = Query(min_length=2, max_length=100),
                       limit: int = Query(default=40, ge=1, le=50)):
    _actor("platform.external_products.view")
    with engine.connect() as conn:
        items = suggest_verified_categories(conn, query, limit=limit)
    return {"items": items, "total": len(items), "verified_only": True,
            "suggestions_are_not_confirmed": True}


@router.post("/bulk-confirm")
def confirm(payload: ConfirmationBatch):
    actor = _actor("platform.external_products.link_existing")
    try:
        with engine.begin() as conn:
            result = confirm_cbs_batch(conn, [d.model_dump() for d in payload.selections], actor_id=str(actor.user_id))
        return result
    except CBSConcurrentChange as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (CBSDecisionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/bulk-remove")
def remove(payload: RemovalBatch):
    actor = _actor("platform.external_products.link_existing")
    try:
        with engine.begin() as conn:
            result = remove_cbs_batch(conn, [d.model_dump() for d in payload.selections], actor_id=str(actor.user_id))
        return result
    except CBSConcurrentChange as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (CBSDecisionError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
