from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from app.db import engine
from app.services.authorization_foundation_service import permissions_for_session_role
from app.services.server_session_service import SESSION_COOKIE_NAME, resolve_server_session
from app.services.shopping_list_service import (
    add_shopping_list_item,
    complete_active_shopping_list,
    delete_shopping_list_item,
    get_active_shopping_list,
    update_shopping_list_item,
)

router = APIRouter()


def _session_context(request: Request, required_permission: str):
    raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    with engine.begin() as conn:
        context = resolve_server_session(conn, raw_session_id)
    permissions = permissions_for_session_role(context.role)
    if required_permission not in permissions:
        raise HTTPException(status_code=403, detail="Geen bevoegdheid voor Winkelen")
    return context


@router.get("/api/shopping-list")
def shopping_list_get(request: Request):
    context = _session_context(request, "shopping_list.view")
    with engine.begin() as conn:
        return get_active_shopping_list(conn, context.active_household_id)


@router.post("/api/shopping-list/items", status_code=201)
def shopping_list_item_create(
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    context = _session_context(request, "shopping_list.update")
    try:
        with engine.begin() as conn:
            item = add_shopping_list_item(conn, context.active_household_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return item


@router.put("/api/shopping-list/items/{item_id}")
def shopping_list_item_update(
    item_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    context = _session_context(request, "shopping_list.update")
    try:
        with engine.begin() as conn:
            item = update_shopping_list_item(
                conn,
                context.active_household_id,
                item_id,
                payload,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Winkellijstregel niet gevonden")
    return item


@router.delete("/api/shopping-list/items/{item_id}", status_code=204)
def shopping_list_item_delete(item_id: str, request: Request):
    context = _session_context(request, "shopping_list.update")
    with engine.begin() as conn:
        deleted = delete_shopping_list_item(conn, context.active_household_id, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Winkellijstregel niet gevonden")
    return None


@router.post("/api/shopping-list/complete")
def shopping_list_complete(request: Request):
    context = _session_context(request, "shopping_list.manage")
    with engine.begin() as conn:
        return complete_active_shopping_list(
            conn,
            context.active_household_id,
            context.user_id,
        )
