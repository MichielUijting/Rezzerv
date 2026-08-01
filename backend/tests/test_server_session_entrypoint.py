from fastapi.routing import APIRoute

from app.session_entrypoint import SESSION_ROUTE_METHODS, app


def _route_count(path: str, method: str) -> int:
    return sum(
        1
        for route in app.router.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in set(route.methods or set())
    )


def test_each_server_session_route_is_registered_exactly_once():
    for path, method in SESSION_ROUTE_METHODS:
        assert _route_count(path, method) == 1


def test_existing_health_route_is_preserved():
    assert _route_count('/api/health', 'GET') == 1


def test_login_route_uses_server_session_module():
    login_routes = [
        route
        for route in app.router.routes
        if isinstance(route, APIRoute)
        and route.path == '/api/auth/login'
        and 'POST' in set(route.methods or set())
    ]

    assert len(login_routes) == 1
    assert login_routes[0].endpoint.__module__ == 'app.api.server_session_routes'
