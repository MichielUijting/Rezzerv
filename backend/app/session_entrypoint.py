"""Rezzerv runtime entrypoint for the server-side session migration.

The existing application remains the single application instance. This module
replaces the legacy authentication endpoints and redirects the central legacy
route guards to the server-side session context. Unrelated routes retain their
existing implementation and order.
"""

from __future__ import annotations

from contextvars import ContextVar

from fastapi import Request
from fastapi.routing import APIRoute

import app.main as legacy_main
from app.main import app
from app.api.server_session_routes import create_server_session_router
from app.api.superuser_routes import create_superuser_router
from app.api.superuser_household_routes import create_superuser_household_router
from app.api.support_broadcast_routes import router as support_broadcast_router
from app.services.actor_attribution_service import install_actor_attribution_tracking
from app.services.authorization_ui_fixture_provisioning import (
    ensure_authorization_ui_fixture_member,
)
from app.services.membership_user_identity_service import backfill_membership_user_ids
from app.services.session_request_context import (
    authorized_household_id_from_session,
    bind_current_actor_from_request_session_if_available,
    bind_request_session,
    household_context_from_session,
    legacy_user_payload_from_session,
    request_household_id_from_session,
    require_household_admin_from_session,
    require_platform_admin_from_session,
    reset_request_session,
)
from app.services.support_message_session_adapter import household_support_actor
from app.services.system_superuser_session_provisioning import (
    ensure_system_superuser_for_session_runtime,
)


SESSION_ROUTE_METHODS = {
    ("/api/auth/login", "POST"),
    ("/api/auth/logout", "POST"),
    ("/api/session", "GET"),
}

ADMIN_ONLY_RUNTIME_PATHS = {
    ("/api/testing/fixtures/receipt-export/generate", "POST"),
}

MANUAL_RECEIPT_IMPORT_ROUTE = ("/api/receipts/import", "POST")
_manual_receipt_import_context: ContextVar[bool] = ContextVar(
    "rezzerv_manual_receipt_import_context",
    default=False,
)
_original_import_uploaded_receipt_payload = legacy_main.import_uploaded_receipt_payload


def _import_uploaded_receipt_payload_with_manual_review_fallback(*args, **kwargs):
    """Persist a reviewable receipt row when a manual Kassa upload is not classified.

    The raw file has already been accepted by the manual import endpoint. For this
    route only, a negative receipt classification must therefore result in a
    receipt_tables row that remains visible as 'Controle nodig' instead of leaving
    only an orphan raw upload. Other ingestion paths keep their existing policy.
    """

    if _manual_receipt_import_context.get():
        kwargs["create_failed_receipt_table"] = True
    return _original_import_uploaded_receipt_payload(*args, **kwargs)


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
    legacy_main.require_household_admin_context = require_household_admin_from_session
    legacy_main.resolve_authorized_household_id = authorized_household_id_from_session
    legacy_main.get_request_household_id = request_household_id_from_session
    legacy_main.require_platform_admin_user = require_platform_admin_from_session
    legacy_main.import_uploaded_receipt_payload = _import_uploaded_receipt_payload_with_manual_review_fallback

    from app.api import support_message_routes
    support_message_routes._household_actor = household_support_actor


@app.middleware("http")
async def server_session_request_context(request: Request, call_next):
    token = bind_request_session(request)
    route_key = (request.url.path, request.method.upper())
    manual_receipt_token = _manual_receipt_import_context.set(
        route_key == MANUAL_RECEIPT_IMPORT_ROUTE
    )
    try:
        # Bind the canonical actor before any route/service can write domain data.
        # Public requests without a valid server session remain unattributed.
        bind_current_actor_from_request_session_if_available()
        if route_key in ADMIN_ONLY_RUNTIME_PATHS:
            require_platform_admin_from_session(None)
        return await call_next(request)
    finally:
        _manual_receipt_import_context.reset(manual_receipt_token)
        reset_request_session(token)


def activate_server_side_session_routes() -> None:
    """Replace legacy auth routes without touching unrelated application routes."""

    app.router.routes[:] = [
        route for route in app.router.routes if not _is_replaced_session_route(route)
    ]
    app.include_router(create_server_session_router(legacy_main.engine))
    app.include_router(create_superuser_router(legacy_main.engine))
    app.include_router(create_superuser_household_router(legacy_main.engine))
    app.include_router(support_broadcast_router)

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


with legacy_main.engine.begin() as provisioning_conn:
    ensure_system_superuser_for_session_runtime(provisioning_conn)
    ensure_authorization_ui_fixture_member(provisioning_conn)
    backfill_membership_user_ids(provisioning_conn)

install_actor_attribution_tracking(legacy_main.engine)
activate_server_side_route_context()
activate_server_side_session_routes()
