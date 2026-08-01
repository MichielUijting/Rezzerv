"""Rezzerv runtime entrypoint for the server-side session migration.

The existing application remains the single application instance. This module
replaces the legacy authentication endpoints and redirects the central legacy
route guards to the server-side session context. Unrelated routes retain their
existing implementation and order.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.routing import APIRoute

import app.main as legacy_main
from app.main import app
from app.api.server_session_routes import router as server_session_router
from app.services.session_request_context import (
    authorized_household_id_from_session,
    bind_request_session,
    household_context_from_session,
    legacy_user_payload_from_session,
    request_household_id_from_session,
    require_platform_admin_from_session,
    reset_request_session,
)


SESSION_ROUTE_METHODS = {
    ("/api/auth/login", "POST"),
    ("/api/auth/logout", "POST"),
    ("/api/session", "GET"),
}

ADMIN_ONLY_RUNTIME_PATHS = {
    ("/api/testing/fixtures/receipt-export/generate", "POST"),
}


def _is_replaced_session_route(route) -> bool:
    if not isinstance(route, APIRoute):
        return False
    route_methods = set(route.methods or set())
    return any(
        route.path == path and method in route_methods
        for path, method in SESSION_ROUTE_METHODS
    )


def activate_server_side_route_context() -> None:
    """Make the server session the sole authority for existing route guards."""

    legacy_main.get_current_user_from_authorization = legacy_user_payload_from_session
    legacy_main.require_household_context = household_context_from_session
    legacy_main.resolve_authorized_household_id = authorized_household_id_from_session
    legacy_main.get_request_household_id = request_household_id_from_session
    legacy_main.require_platform_admin_user = require_platform_admin_from_session


@app.middleware("http")
async def server_session_request_context(request: Request, call_next):
    token = bind_request_session(request)
    try:
        route_key = (request.url.path, request.method.upper())
        if route_key in ADMIN_ONLY_RUNTIME_PATHS:
            require_platform_admin_from_session(None)
        return await call_next(request)
    finally:
        reset_request_session(token)


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


activate_server_side_route_context()
activate_server_side_session_routes()
