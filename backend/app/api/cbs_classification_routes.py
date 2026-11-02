"""CBS classification API, independent of GS1 and Shopify authorities.

Only authenticated platform Superusers and Frontteam with canonical privileges
may confirm or remove classifications; clients never supply role or actor IDs.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.db import engine
from app.services.cbs_classification_service import (
    CBSConcurrentChange,
    CBSDecisionError,
    confirm_cbs_batch,
    remove_cbs_batch,
    search_verified_categories,
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


@router.get("/categories")
def categories(query: str = Query(min_length=2, max_length=100), limit: int = Query(default=40, ge=1, le=50)):
    _actor("platform.external_products.view")
    with engine.connect() as conn:
        items = search_verified_categories(conn, query, limit=limit)
    return {"items": items, "total": len(items), "verified_only": True}


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
