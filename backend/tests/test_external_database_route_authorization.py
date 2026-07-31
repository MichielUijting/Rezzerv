from __future__ import annotations

from fastapi.routing import APIRoute

from app.api.system_routes import router


def _route(method: str, path: str) -> APIRoute:
    for candidate in router.routes:
        if isinstance(candidate, APIRoute) and candidate.path == path and method in candidate.methods:
            return candidate
    raise AssertionError(f"Route ontbreekt: {method} {path}")


def _dependency_names(route: APIRoute) -> set[str]:
    return {
        str(getattr(dependency.call, "__name__", ""))
        for dependency in route.dependant.dependencies
    }


def test_external_database_routes_have_explicit_platform_permissions() -> None:
    expected = {
        ("POST", "/api/external-databases/catalog/promote-candidate"): "require_external_databases_manage",
        ("GET", "/api/external-databases/summary"): "require_external_databases_view",
        ("GET", "/api/external-databases/retailers"): "require_external_databases_view",
        ("POST", "/api/external-databases/retailers/{retailer_code}/match-preview"): "require_external_databases_view",
        ("POST", "/api/external-databases/retailers/{retailer_code}/diagnose-real-candidates"): "require_external_databases_view",
        ("POST", "/api/external-databases/retailers/{retailer_code}/save-candidates"): "require_external_databases_update",
        ("POST", "/api/external-products/off/search"): "require_external_databases_view",
        ("POST", "/api/external-databases/off/search-preview"): "require_external_databases_view",
        ("POST", "/api/external-databases/off/save-candidates"): "require_external_databases_update",
        ("GET", "/api/external-databases/receipt-items"): "require_external_databases_view",
        ("POST", "/api/external-databases/receipt-items/ensure-candidates"): "require_external_databases_update",
        ("POST", "/api/external-databases/coverage/receipt-items"): "require_external_databases_view",
        ("GET", "/api/external-databases/candidates"): "require_external_databases_view",
        ("POST", "/api/external-databases/catalog/promote-highest"): "require_external_databases_manage",
        ("POST", "/api/external-databases/catalog/unlink"): "require_external_databases_manage",
        ("GET", "/api/external-databases/catalog/products"): "require_external_databases_view",
        ("GET", "/api/admin/external-relations/batch"): "require_external_databases_manage",
        ("POST", "/api/admin/external-relations/batch/decision"): "require_external_databases_manage",
    }

    for route_key, required_dependency in expected.items():
        route = _route(*route_key)
        assert required_dependency in _dependency_names(route), (
            f"{route_key[0]} {route_key[1]} mist centrale dependency {required_dependency}"
        )


def test_all_external_database_routes_are_covered_by_contract() -> None:
    covered = {
        (method, route.path)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if route.path.startswith("/api/external-databases/")
    }

    expected_paths = {
        ("POST", "/api/external-databases/catalog/promote-candidate"),
        ("GET", "/api/external-databases/summary"),
        ("GET", "/api/external-databases/retailers"),
        ("POST", "/api/external-databases/retailers/{retailer_code}/match-preview"),
        ("POST", "/api/external-databases/retailers/{retailer_code}/diagnose-real-candidates"),
        ("POST", "/api/external-databases/retailers/{retailer_code}/save-candidates"),
        ("POST", "/api/external-databases/off/search-preview"),
        ("POST", "/api/external-databases/off/save-candidates"),
        ("GET", "/api/external-databases/receipt-items"),
        ("POST", "/api/external-databases/receipt-items/ensure-candidates"),
        ("POST", "/api/external-databases/coverage/receipt-items"),
        ("GET", "/api/external-databases/candidates"),
        ("POST", "/api/external-databases/catalog/promote-highest"),
        ("POST", "/api/external-databases/catalog/unlink"),
        ("GET", "/api/external-databases/catalog/products"),
    }

    assert covered == expected_paths
