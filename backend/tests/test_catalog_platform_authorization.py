from fastapi.routing import APIRoute

from app.api.catalog_routes import router


def _dependency_names(route: APIRoute) -> set[str]:
    return {
        getattr(dependency.dependency, "__name__", "")
        for dependency in route.dependencies
    }


def test_alle_catalogusroutes_hebben_centrale_leesbeveiliging():
    catalog_routes = [
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/catalog")
    ]
    assert catalog_routes
    for route in catalog_routes:
        assert "require_catalog_view" in _dependency_names(route), (
            f"Catalogusroute zonder centrale leesbeveiliging: {sorted(route.methods or [])} {route.path}"
        )


def test_catalogusrouter_bevat_lees_en_gpc_mutatieroutes():
    manifest = {
        (method, route.path)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in (route.methods or set())
    }
    assert ("GET", "/api/catalog") in manifest
    assert ("GET", "/api/catalog/{global_product_id}") in manifest
    assert ("PUT", "/api/catalog/{global_product_id}/gpc-brick") in manifest
    assert ("DELETE", "/api/catalog/{global_product_id}/gpc-brick") in manifest
