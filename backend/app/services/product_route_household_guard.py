from __future__ import annotations

import re
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text


PLATFORM_ADMIN_MUTATIONS = {
    ("POST", "/api/external-databases/catalog/promote-candidate-with-product-type"),
    ("POST", "/api/external-products/off/link"),
    ("POST", "/api/product-groups"),
    ("PUT", "/api/product-groups/{inventory_group_key:path}"),
    ("DELETE", "/api/product-groups/{inventory_group_key:path}"),
    ("POST", "/api/products/{global_product_id}/inventory-group"),
}
AUTHENTICATED_ROUTES = {
    ("GET", "/api/external-databases/catalog/products"),
    ("POST", "/api/external-products/off/search"),
    ("GET", "/api/product-groups"),
}
_INVENTORY_GROUP_ASSIGNMENT = re.compile(r"^/api/inventory/items/([^/]+)/group$")
_PRODUCT_GROUP_ITEM = re.compile(r"^/api/product-groups/(.+)$")
_PRODUCT_INVENTORY_GROUP = re.compile(r"^/api/products/([^/]+)/inventory-group$")


def canonical_route_key(method: str, path: str) -> tuple[str, str]:
    normalized_method = str(method or "").upper()
    normalized_path = str(path or "")
    if _PRODUCT_GROUP_ITEM.match(normalized_path):
        return normalized_method, "/api/product-groups/{inventory_group_key:path}"
    if _PRODUCT_INVENTORY_GROUP.match(normalized_path):
        return normalized_method, "/api/products/{global_product_id}/inventory-group"
    return normalized_method, normalized_path


def is_guarded_product_route(method: str, path: str) -> bool:
    route_key = canonical_route_key(method, path)
    return bool(
        route_key in PLATFORM_ADMIN_MUTATIONS
        or route_key in AUTHENTICATED_ROUTES
        or route_key == ("GET", "/api/inventory/groups")
        or (str(method or "").upper() == "GET" and str(path or "") == "/api/store-review-articles")
        or _INVENTORY_GROUP_ASSIGNMENT.match(str(path or ""))
    )


def resolve_inventory_household(conn, path: str) -> str | None:
    match = _INVENTORY_GROUP_ASSIGNMENT.match(str(path or ""))
    if not match:
        return None
    inventory_id = match.group(1).strip()
    row = conn.execute(
        text("SELECT household_id FROM inventory WHERE id = :inventory_id LIMIT 1"),
        {"inventory_id": inventory_id},
    ).mappings().first()
    if not row or not str(row.get("household_id") or "").strip():
        raise HTTPException(status_code=404, detail="Voorraadregel niet gevonden")
    return str(row["household_id"]).strip()


def authorize_product_route_request(
    conn,
    method: str,
    path: str,
    authorization: str | None,
    requested_household_id: str | None,
    require_household_context: Callable[[str | None, str | None], dict[str, Any]],
    require_inventory_write_context: Callable[[str | None, str | None], dict[str, Any]],
    require_platform_admin_user: Callable[[str | None], object],
) -> dict[str, Any] | object | None:
    route_key = canonical_route_key(method, path)
    if route_key in PLATFORM_ADMIN_MUTATIONS:
        return require_platform_admin_user(authorization)
    if route_key == ("GET", "/api/inventory/groups"):
        return require_household_context(authorization, requested_household_id)
    if route_key in AUTHENTICATED_ROUTES:
        return require_household_context(authorization, None)
    inventory_household_id = resolve_inventory_household(conn, path)
    if inventory_household_id is not None:
        return require_inventory_write_context(authorization, inventory_household_id)
    return None


def build_store_review_articles(main_module, household_id: str, query: str) -> list[dict[str, Any]]:
    normalized_query = str(query or "").strip().lower()
    items = [dict(item) for item in main_module.MOCK_ARTICLE_OPTIONS]
    seen_names = {str(item.get("name") or "").strip().lower() for item in items if item.get("name")}
    with main_module.engine.begin() as conn:
        household_rows = conn.execute(
            text(
                """
                SELECT id, naam AS article_name, consumable, brand_or_maker
                FROM household_articles
                WHERE household_id = :household_id
                  AND trim(COALESCE(naam, '')) <> ''
                ORDER BY lower(naam) ASC, id ASC
                """
            ),
            {"household_id": household_id},
        ).mappings().all()
        defaults_by_article = main_module.get_household_article_location_defaults(
            conn,
            [str(row.get("id") or "") for row in household_rows],
        )
        for row in household_rows:
            article_name = str(row.get("article_name") or "").strip()
            normalized = article_name.lower()
            if not article_name or normalized in seen_names:
                continue
            defaults = defaults_by_article.get(str(row.get("id") or ""), {})
            items.append(
                {
                    "id": str(row.get("id") or ""),
                    "name": article_name,
                    "brand": str(row.get("brand_or_maker") or "").strip(),
                    "consumable": bool(row["consumable"]) if row.get("consumable") is not None else main_module.infer_consumable_from_name(article_name),
                    "default_location_id": defaults.get("default_location_id") or "",
                    "default_sublocation_id": defaults.get("default_sublocation_id") or "",
                }
            )
            seen_names.add(normalized)
        inventory_names = conn.execute(
            text(
                """
                SELECT DISTINCT naam AS article_name
                FROM inventory
                WHERE household_id = :household_id
                  AND trim(COALESCE(naam, '')) <> ''
                ORDER BY lower(naam) ASC
                """
            ),
            {"household_id": household_id},
        ).mappings().all()
        for row in inventory_names:
            article_name = str(row.get("article_name") or "").strip()
            normalized = article_name.lower()
            if not article_name or normalized in seen_names:
                continue
            items.append(
                {
                    "id": main_module.build_live_article_option_id(article_name),
                    "name": article_name,
                    "brand": "",
                    "consumable": main_module.infer_consumable_from_name(article_name),
                }
            )
            seen_names.add(normalized)
    return [
        item
        for item in items
        if not normalized_query
        or normalized_query in f"{item.get('name') or ''} {item.get('brand') or ''}".lower()
    ]


def install_product_route_household_guard(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "product_route_household_guard_installed", False):
        return

    @app.middleware("http")
    async def product_route_household_guard(request, call_next):
        if not is_guarded_product_route(request.method, request.url.path):
            return await call_next(request)
        try:
            if request.method.upper() == "GET" and request.url.path == "/api/store-review-articles":
                context = main_module.require_household_context(
                    request.headers.get("authorization"),
                    None,
                )
                household_id = str(context["active_household_id"])
                return JSONResponse(
                    content=build_store_review_articles(
                        main_module,
                        household_id,
                        request.query_params.get("q", ""),
                    )
                )
            if _INVENTORY_GROUP_ASSIGNMENT.match(request.url.path):
                with main_module.engine.begin() as conn:
                    authorize_product_route_request(
                        conn,
                        request.method,
                        request.url.path,
                        request.headers.get("authorization"),
                        request.query_params.get("household_id"),
                        main_module.require_household_context,
                        main_module.require_inventory_write_context,
                        main_module.require_platform_admin_user,
                    )
            else:
                authorize_product_route_request(
                    None,
                    request.method,
                    request.url.path,
                    request.headers.get("authorization"),
                    request.query_params.get("household_id"),
                    main_module.require_household_context,
                    main_module.require_inventory_write_context,
                    main_module.require_platform_admin_user,
                )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or None,
            )
        return await call_next(request)

    app.state.product_route_household_guard_installed = True
