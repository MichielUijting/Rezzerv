from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy import inspect, text

from app.db import engine
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.authorization_membership_service import (
    AuthorizationDeniedError,
    migrate_legacy_household_memberships,
    require_household_permission,
)
from app.services.server_session_service import SESSION_COOKIE_NAME, resolve_server_session
from app.services.shopping_list_service import (
    add_shopping_list_item,
    complete_active_shopping_list,
    delete_shopping_list_item,
    get_active_shopping_list,
    update_shopping_list_item,
)

router = APIRouter()


def _membership_id(conn, *, household_id: str, user_id: str, email: str) -> str:
    columns = {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns("household_memberships")
    }
    membership_id_column = "id" if "id" in columns else (
        "membership_id" if "membership_id" in columns else (
            "user_email" if "user_email" in columns else (
                "user_id" if "user_id" in columns else None
            )
        )
    )
    if not membership_id_column:
        raise HTTPException(status_code=403, detail="Huishoudlidmaatschap heeft geen geldige identificatie")

    active_condition = (
        "AND lower(trim(COALESCE(status, 'active'))) = 'active'"
        if "status" in columns
        else ""
    )
    if "user_email" in columns:
        row = conn.execute(text(f"""
            SELECT {membership_id_column} AS membership_id
            FROM household_memberships
            WHERE household_id = :household_id
              AND lower(trim(user_email)) = lower(trim(:email))
              {active_condition}
            LIMIT 1
        """), {"household_id": household_id, "email": email}).mappings().first()
    elif "user_id" in columns:
        row = conn.execute(text(f"""
            SELECT {membership_id_column} AS membership_id
            FROM household_memberships
            WHERE household_id = :household_id
              AND user_id = :user_id
              {active_condition}
            LIMIT 1
        """), {"household_id": household_id, "user_id": user_id}).mappings().first()
    else:
        raise HTTPException(status_code=403, detail="Huishoudlidmaatschap kan niet worden vastgesteld")

    if not row:
        raise HTTPException(status_code=403, detail="Geen actief huishoudlidmaatschap gevonden")
    return str(row["membership_id"])


def _authorized_context(conn, request: Request, required_permission: str):
    raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    context = resolve_server_session(conn, raw_session_id)
    ensure_authorization_foundation(conn)
    migrate_legacy_household_memberships(conn)
    membership_id = _membership_id(
        conn,
        household_id=context.active_household_id,
        user_id=context.user_id,
        email=context.email,
    )
    try:
        require_household_permission(
            conn,
            household_id=context.active_household_id,
            membership_id=membership_id,
            permission_key=required_permission,
        )
    except AuthorizationDeniedError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "authorization_denied",
                "permission_key": exc.decision.permission_key,
                "reason": exc.decision.reason,
            },
        ) from exc
    return context


@router.get("/api/shopping-list")
def shopping_list_get(request: Request):
    with engine.begin() as conn:
        context = _authorized_context(conn, request, "shopping_list.view")
        return get_active_shopping_list(conn, context.active_household_id)


@router.post("/api/shopping-list/items", status_code=201)
def shopping_list_item_create(
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    try:
        with engine.begin() as conn:
            context = _authorized_context(conn, request, "shopping_list.update")
            return add_shopping_list_item(conn, context.active_household_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/shopping-list/items/{item_id}")
def shopping_list_item_update(
    item_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
):
    try:
        with engine.begin() as conn:
            context = _authorized_context(conn, request, "shopping_list.update")
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
    with engine.begin() as conn:
        context = _authorized_context(conn, request, "shopping_list.update")
        deleted = delete_shopping_list_item(conn, context.active_household_id, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Winkellijstregel niet gevonden")
    return None


@router.post("/api/shopping-list/complete")
def shopping_list_complete(request: Request):
    with engine.begin() as conn:
        context = _authorized_context(conn, request, "shopping_list.manage")
        return complete_active_shopping_list(
            conn,
            context.active_household_id,
            context.user_id,
        )
