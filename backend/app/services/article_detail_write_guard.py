from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse

_TARGET_ENDPOINTS = {
    "enrich_article_by_id",
    "patch_article_household_details",
}
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def discover_article_detail_write_routes(app) -> set[tuple[str, str]]:
    protected: set[tuple[str, str]] = set()
    for route in getattr(app, "routes", []):
        endpoint = getattr(route, "endpoint", None)
        endpoint_name = getattr(endpoint, "__name__", "")
        if endpoint_name not in _TARGET_ENDPOINTS:
            continue
        path = str(getattr(route, "path", "") or "")
        for method in set(getattr(route, "methods", set()) or set()):
            normalized_method = str(method).upper()
            if path and normalized_method in _WRITE_METHODS:
                protected.add((normalized_method, path))
    return protected


def install_article_detail_write_guard(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "article_detail_write_guard_installed", False):
        return

    protected_routes = discover_article_detail_write_routes(app)

    @app.middleware("http")
    async def article_detail_write_guard(request, call_next):
        route_key = (request.method.upper(), request.url.path)
        matched = route_key in protected_routes
        if not matched:
            for method, template in protected_routes:
                if method != request.method.upper():
                    continue
                template_parts = template.strip("/").split("/")
                request_parts = request.url.path.strip("/").split("/")
                if len(template_parts) != len(request_parts):
                    continue
                if all(tp.startswith("{") and tp.endswith("}") or tp == rp for tp, rp in zip(template_parts, request_parts)):
                    matched = True
                    break
        if matched:
            try:
                main_module.require_inventory_write_context(
                    request.headers.get("authorization"),
                    None,
                )
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=exc.headers or None,
                )
        return await call_next(request)

    app.state.article_detail_write_guard_routes = protected_routes
    app.state.article_detail_write_guard_installed = True
