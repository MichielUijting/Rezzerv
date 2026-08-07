from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException

from app.db import engine
from app.api.authorization_membership_routes import _actor_context, _require
from app.services.day_article_service import (
    DIRECT_CONSUMPTION,
    get_default_inventory_handling,
    record_direct_consumption,
    set_default_inventory_handling,
)

router = APIRouter(tags=["unpacking-day-articles"])


@router.get("/api/households/{household_id}/articles/{household_article_id}/inventory-handling")
def get_article_inventory_handling(
    household_id: str,
    household_article_id: str,
    authorization: str | None = Header(default=None),
):
    del authorization
    with engine.begin() as conn:
        context = _actor_context(conn, household_id)
        _require(conn, context, "articles.view")
        try:
            return get_default_inventory_handling(conn, household_id, household_article_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/api/households/{household_id}/articles/{household_article_id}/inventory-handling")
def update_article_inventory_handling(
    household_id: str,
    household_article_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    del authorization
    with engine.begin() as conn:
        context = _actor_context(conn, household_id)
        _require(conn, context, "articles.manage")
        try:
            return set_default_inventory_handling(
                conn,
                household_id=household_id,
                household_article_id=household_article_id,
                handling=str(payload.get("default_inventory_handling") or ""),
                actor_user_id=context["user_id"],
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/households/{household_id}/articles/{household_article_id}/direct-consumption")
def process_direct_consumption(
    household_id: str,
    household_article_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    del authorization
    with engine.begin() as conn:
        context = _actor_context(conn, household_id)
        _require(conn, context, "unpacking.process")
        try:
            result = record_direct_consumption(
                conn,
                household_id=household_id,
                household_article_id=household_article_id,
                quantity=Decimal(str(payload.get("quantity") or "0")),
                idempotency_key=str(payload.get("idempotency_key") or ""),
                actor_user_id=context["user_id"],
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ArithmeticError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if result["handling"] != DIRECT_CONSUMPTION:
            raise HTTPException(status_code=500, detail="Onverwachte voorraadverwerking")
        return result
