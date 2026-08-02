from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from sqlalchemy import inspect, text

from app.db import engine
from app.services.article_group_secure_store import (
    list_article_groups,
    list_household_articles_for_grouping,
)
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
    search_shopping_catalog,
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


def _project_existing_catalog(scope: str, household_id: str, query: str, limit: int) -> dict[str, Any] | None:
    normalized_query = " ".join(str(query or "").strip().split())
    if len(normalized_query) < 2:
        return {"scope": scope, "query": normalized_query, "items": [], "total": 0}
    query_lower = normalized_query.lower()

    if scope == "household_articles":
        payload = list_household_articles_for_grouping(household_id=household_id)
        source_items = payload.get("items") or []
        items = []
        for item in source_items:
            label = str(item.get("article_name") or "").strip()
            if query_lower not in label.lower():
                continue
            items.append({
                "source_type": "household_article",
                "source_id": str(item.get("id") or ""),
                "label": label,
                "article_name": label,
                "article_group_name": str(item.get("article_group_name") or ""),
                "product_type_name": str(item.get("product_type_name") or ""),
            })
            if len(items) >= limit:
                break
        return {"scope": scope, "query": normalized_query, "items": items, "total": len(items)}

    if scope == "article_groups":
        payload = list_article_groups(household_id=household_id)
        source_items = payload.get("items") or []
        items = []
        for item in source_items:
            label = str(item.get("name") or "").strip()
            if query_lower not in label.lower():
                continue
            items.append({
                "source_type": "article_group",
                "source_id": str(item.get("id") or ""),
                "label": label,
                "article_name": label,
                "article_group_name": label,
                "product_type_name": "",
            })
            if len(items) >= limit:
                break
        return {"scope": scope, "query": normalized_query, "items": items, "total": len(items)}

    return None


@router.get("/api/shopping-list")
def shopping_list_get(request: Request):
    with engine.begin() as conn:
        context = _authorized_context(conn, request, "shopping_list.view")
        return get_active_shopping_list(conn, context.active_household_id)


@router.get("/api/shopping-list/catalog-search")
def shopping_list_catalog_search(
    request: Request,
    scope: str = Query(...),
    query: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=50),
):
    normalized_scope = str(scope or "").strip().lower()
    try:
        with engine.begin() as conn:
            context = _authorized_context(conn, request, "shopping_list.view")
            active_household_id = str(context.active_household_id)

        existing_projection = _project_existing_catalog(
            normalized_scope,
            active_household_id,
            query,
            limit,
        )
        if existing_projection is not None:
            return existing_projection

        with engine.begin() as conn:
            return search_shopping_catalog(
                conn,
                active_household_id,
                scope=normalized_scope,
                query=query,
                limit=limit,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
