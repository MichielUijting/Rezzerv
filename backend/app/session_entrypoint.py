"""Rezzerv runtime entrypoint for the server-side session migration.

The existing application remains the single application instance.  This module
removes only the legacy authentication endpoints and then mounts the new
cookie-based session router exactly once.  All unrelated routes keep their
existing order and implementation.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from app.main import app
from app.api.server_session_routes import router as server_session_router


SESSION_ROUTE_METHODS = {
    ("/api/auth/login", "POST"),
    ("/api/auth/logout", "POST"),
    ("/api/session", "GET"),
}


def _is_replaced_session_route(route) -> bool:
    if not isinstance(route, APIRoute):
        return False
    route_methods = set(route.methods or set())
    return any(
        route.path == path and method in route_methods
        for path, method in SESSION_ROUTE_METHODS
    )


def activate_server_side_session_routes() -> None:
    """Replace legacy auth routes without touching unrelated application routes."""

    app.router.routes[:] = [
        route for route in app.router.routes if not _is_replaced_session_route(route)
    ]
    app.include_router(server_session_router)

    registered = {
        (route.path, method)
        for route in app.router.routes
        if isinstance(route, APIRoute)
        for method in (route.methods or set())
        if (route.path, method) in SESSION_ROUTE_METHODS
    }
    if registered != SESSION_ROUTE_METHODS:
        missing = sorted(SESSION_ROUTE_METHODS - registered)
        raise RuntimeError(f"Server-side sessieroutes incompleet: {missing}")

    duplicates = []
    for path, method in SESSION_ROUTE_METHODS:
        count = sum(
            1
            for route in app.router.routes
            if isinstance(route, APIRoute)
            and route.path == path
            and method in set(route.methods or set())
        )
        if count != 1:
            duplicates.append(f"{method} {path}: {count}")
    if duplicates:
        raise RuntimeError(
            "Server-side sessieroutes niet uniek geregistreerd: " + ", ".join(duplicates)
        )


activate_server_side_session_routes()
