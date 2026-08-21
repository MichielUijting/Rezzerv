from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from sqlalchemy import inspect, text

from app.db import engine
from app.services.article_group_secure_store import (
    list_article_groups,
    list_household_articles_for_grouping,
)
from app.services.authorization_membership_service import (
    AuthorizationDeniedError,
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
CATALOG_SCOPES = ("household_articles", "product_types", "article_groups")
SOURCE_PRIORITY = {"household_article": 0, "product_type": 1, "article_group": 2}


def _membership_id(conn, *, household_id: str, user_id: str, email: str) -> str:
    columns = {str(column.get("name") or "") for column in inspect(conn).get_columns("household_memberships")}
    membership_id_column = "id" if "id" in columns else (
        "membership_id" if "membership_id" in columns else (
            "user_email" if "user_email" in columns else ("user_id" if "user_id" in columns else None)
        )
    )
    if not membership_id_column:
        raise HTTPException(status_code=403, detail="Huishoudlidmaatschap heeft geen geldige identificatie")

    active_condition = "AND lower(trim(COALESCE(status, 'active'))) = 'active'" if "status" in columns else ""
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


def _search_one_scope(scope: str, household_id: str, query: str, limit: int) -> dict[str, Any]:
    projected = _project_existing_catalog(scope, household_id, query, limit)
    if projected is not None:
        return projected
    with engine.begin() as conn:
        return search_shopping_catalog(
            conn,
            household_id,
            scope=scope,
            query=query,
            limit=limit,
        )


def _relevance_key(item: dict[str, Any], query: str) -> tuple[int, int, str]:
    label = str(item.get("label") or "").strip().lower()
    needle = str(query or "").strip().lower()
    match_rank = 0 if label == needle else (1 if label.startswith(needle) else 2)
    source_rank = SOURCE_PRIORITY.get(str(item.get("source_type") or ""), 9)
    return match_rank, source_rank, label


@router.get("/api/shopping-list")
def shopping_list_get(request: Request):
    with engine.begin() as conn:
        context = _authorized_context(conn, request, "shopping_list.view")
        return get_active_shopping_list(conn, context.active_household_id)


@router.get("/api/shopping-list/catalog-search")
def shopping_list_catalog_search(
    request: Request,
    scope: str = Query(default="all"),
    query: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=50),
):
    normalized_scope = str(scope or "all").strip().lower()
    if normalized_scope != "all" and normalized_scope not in CATALOG_SCOPES:
        raise HTTPException(status_code=400, detail="Ongeldige zoekbron")

    try:
        with engine.begin() as conn:
            context = _authorized_context(conn, request, "shopping_list.view")
            household_id = context.active_household_id

        if normalized_scope != "all":
            return _search_one_scope(normalized_scope, household_id, query, limit)

        normalized_query = " ".join(str(query or "").strip().split())
        if len(normalized_query) < 2:
            return {
                "scope": "all",
                "query": normalized_query,
                "items": [],
                "total": 0,
                "counts": {"household_article": 0, "product_type": 0, "article_group": 0},
            }

        combined: list[dict[str, Any]] = []
        counts = {"household_article": 0, "product_type": 0, "article_group": 0}
        for catalog_scope in CATALOG_SCOPES:
            payload = _search_one_scope(catalog_scope, household_id, normalized_query, limit)
            scope_items = list(payload.get("items") or [])
            combined.extend(scope_items)
            for item in scope_items:
                source_type = str(item.get("source_type") or "")
                if source_type in counts:
                    counts[source_type] += 1

        deduplicated: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in sorted(combined, key=lambda candidate: _relevance_key(candidate, normalized_query)):
            key = (str(item.get("source_type") or ""), str(item.get("source_id") or item.get("label") or ""))
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(item)
            if len(deduplicated) >= limit:
                break

        return {
            "scope": "all",
            "query": normalized_query,
            "items": deduplicated,
            "total": len(deduplicated),
            "counts": counts,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/shopping-list/items", status_code=201)
def shopping_list_item_create(request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        with engine.begin() as conn:
            context = _authorized_context(conn, request, "shopping_list.update")
            return add_shopping_list_item(conn, context.active_household_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/shopping-list/items/{item_id}")
def shopping_list_item_update(item_id: str, request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    try:
        with engine.begin() as conn:
            context = _authorized_context(conn, request, "shopping_list.update")
            item = update_shopping_list_item(conn, context.active_household_id, item_id, payload)
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
        return complete_active_shopping_list(conn, context.active_household_id, context.user_id)
