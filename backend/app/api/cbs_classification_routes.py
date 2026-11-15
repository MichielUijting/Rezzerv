"""CBS classification API, independent of GS1 and Shopify authorities.

Only authenticated platform Superusers and Frontteam with canonical privileges
may confirm or remove classifications; clients never supply role or actor IDs.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
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
from app.services.catalog_classification_export_service import build_catalog_classification_export
from app.services.catalog_classification_import_service import (
    ImportContractError, MAX_BYTES, read_proposals, preview_import, confirm_import,
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


@router.get("/catalog-export")
def export_catalog_classifications():
    """One authenticated, complete, read-only export; no household or receipt history."""
    _actor("platform.external_products.view")
    with engine.connect() as conn:
        if conn.dialect.name == "postgresql":
            # Configure the DBAPI transaction before the first SELECT. A pooled
            # connection can already have performed a PostgreSQL pre-ping.
            conn = conn.execution_options(
                isolation_level="REPEATABLE READ", postgresql_readonly=True,
            )
        with conn.begin():
            contents = build_catalog_classification_export(conn)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=contents,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="Inhuis_Catalogus_Classificatie_{stamp}.zip"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )



class ClassificationImportDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    product_id: str = Field(min_length=1, max_length=200)
    system: Literal["gpc", "cbs"]
    code: str = Field(min_length=6, max_length=8)
    expected_name: str = Field(min_length=1, max_length=500)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_version: str = ""
    approved: Literal[True]
    allow_replace: bool = False


class ClassificationImportConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decisions: list[ClassificationImportDecision] = Field(min_length=1, max_length=100)


@router.post("/classification-import/preview")
async def preview_catalog_classification_import(request: Request):
    """Parse CSV/Excel in memory and validate against the live official Catalogus."""
    _actor("platform.external_products.view")
    if int(request.headers.get("content-length") or 0) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Importbestand mag maximaal 5 MB zijn.")
    body = await request.body()
    filename = request.headers.get("x-inhuis-filename", "")
    try:
        rows = read_proposals(body, filename)
        with engine.connect() as conn:
            if conn.dialect.name == "postgresql":
                conn = conn.execution_options(
                    isolation_level="REPEATABLE READ", postgresql_readonly=True,
                )
            with conn.begin():
                return preview_import(conn, rows)
    except ImportContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/classification-import/confirm")
def confirm_catalog_classification_import(payload: ClassificationImportConfirmation):
    """Only explicitly approved official codes, all-or-nothing for each batch."""
    actor = _actor("platform.external_products.link_existing")
    if any(item.system == "gpc" for item in payload.decisions):
        # Keep the GS1 authority at least as strict as the existing manual GS1 editor.
        require_platform_permission_from_session("gpc.update")
    try:
        with engine.begin() as conn:
            return confirm_import(
                conn, [item.model_dump() for item in payload.decisions],
                actor_id=str(actor.user_id),
            )
    except ImportContractError as exc:
        reason = str(exc)
        status = 409 if any(word in reason for word in (
            "verouderd", "gewijzigd", "ontbreekt", "andere naam")) else 422
        raise HTTPException(status_code=status, detail=reason) from exc
    except (CBSDecisionError, CBSConcurrentChange) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
