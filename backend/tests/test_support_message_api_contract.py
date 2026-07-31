from app.api.frontteam_support_scope_routes import router as scope_router
from app.api.support_message_routes import router


def _route_manifest(selected_router=router):
    return {
        (method, route.path)
        for route in selected_router.routes
        for method in (route.methods or set())
    }


def test_household_support_routes_are_registered():
    routes = _route_manifest()
    assert ("POST", "/api/support/threads") in routes
    assert ("GET", "/api/support/threads") in routes
    assert ("GET", "/api/support/threads/{thread_id}") in routes
    assert ("POST", "/api/support/threads/{thread_id}/messages") in routes


def test_platform_support_routes_are_registered():
    routes = _route_manifest()
    assert ("GET", "/api/platform/support/threads") in routes
    assert ("POST", "/api/platform/support/threads") in routes
    assert ("GET", "/api/platform/support/threads/{thread_id}") in routes
    assert ("POST", "/api/platform/support/threads/{thread_id}/messages") in routes
    assert ("PATCH", "/api/platform/support/threads/{thread_id}/status") in routes
    assert ("GET", "/api/platform/support/export.csv") in routes


def test_platform_support_scope_route_is_registered():
    routes = _route_manifest(scope_router)
    assert ("GET", "/api/platform/support/bereik") in routes


def test_support_api_does_not_register_login_or_existing_domain_routes():
    paths = {route.path for route in router.routes}
    assert "/api/login" not in paths
    assert not any(path.startswith("/api/inventory") for path in paths)
    assert not any(path.startswith("/api/receipts") for path in paths)
    assert not any(path.startswith("/api/purchase-import") for path in paths)
