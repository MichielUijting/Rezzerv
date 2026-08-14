"""Rezzerv runtime entrypoint for the server-side session migration.

The existing application remains the single application instance. This module
replaces the legacy authentication endpoints and redirects the central legacy
route guards to the server-side session context. Unrelated routes retain their
existing implementation and order.
"""

from __future__ import annotations

from fastapi import Body, HTTPException, Request
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
from app.services.receipt_lifecycle_foundation_service import (
    apply_unpack_receipt_lifecycle_action,
    install_receipt_lifecycle_foundation,
    resolve_receipt_for_unpack_batch,
)
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

    # The existing support-message router originally admitted only household
    # administrators. Rezzerv's functional contract allows every authenticated
    # active household member to contact the superuser and continue that
    # conversation. Platform support routes keep their platform permission gate.
    from app.api import support_message_routes
    support_message_routes._household_actor = household_support_actor


@app.middleware("http")
async def server_session_request_context(request: Request, call_next):
    token = bind_request_session(request)
    try:
        # Bind the canonical actor before any route/service can write domain data.
        # Public requests without a valid server session remain unattributed.
        bind_current_actor_from_request_session_if_available()
        route_key = (request.url.path, request.method.upper())
        if route_key in ADMIN_ONLY_RUNTIME_PATHS:
            require_platform_admin_from_session(None)
        return await call_next(request)
    finally:
        reset_request_session(token)


@app.post("/api/purchase-import-batches/{batch_id}/receipt-lifecycle")
def apply_unpack_receipt_lifecycle(
    batch_id: str,
    payload: dict = Body(default_factory=dict),
):
    """Apply the PO-selected disposition for a receipt currently in Uitpakken."""
    action = str(payload.get("action") or "").strip().lower()
    if action not in {"return_to_kassa", "archive"}:
        raise HTTPException(status_code=400, detail="Kies terugzetten naar Kassa of archiveren")

    with legacy_main.engine.begin() as conn:
        receipt = resolve_receipt_for_unpack_batch(conn, batch_id)
        if not receipt:
            raise HTTPException(status_code=404, detail="Geen kassabon gevonden voor deze Uitpakken-batch")

        household_id = str(receipt.get("household_id") or "").strip()
        context = legacy_main.require_household_context(None, household_id)
        if str(context.get("display_role") or "").strip().lower() == "viewer":
            raise HTTPException(status_code=403, detail="Kijkers mogen kassabonnen niet verwijderen of archiveren")

        try:
            return apply_unpack_receipt_lifecycle_action(
                conn,
                batch_id=batch_id,
                household_id=household_id,
                action=action,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.post("/api/admin/receipts/{receipt_table_id}/restore-archived")
def restore_archived_receipt_to_kassa(receipt_table_id: str):
    """Restore one archived receipt to Kassa. Household admin only."""
    normalized_receipt_id = str(receipt_table_id or "").strip()
    if not normalized_receipt_id:
        raise HTTPException(status_code=400, detail="Kassabon-id ontbreekt")

    with legacy_main.engine.begin() as conn:
        receipt = conn.execute(
            legacy_main.text(
                """
                SELECT id, household_id, raw_receipt_id,
                       COALESCE(workflow_state, 'active') AS workflow_state,
                       deleted_at
                FROM receipt_tables
                WHERE id = :receipt_table_id
                LIMIT 1
                """
            ),
            {"receipt_table_id": normalized_receipt_id},
        ).mappings().first()

        if not receipt:
            raise HTTPException(status_code=404, detail="Kassabon niet gevonden")

        household_id = str(receipt.get("household_id") or "").strip()
        legacy_main.require_household_admin_context(None, household_id)

        if str(receipt.get("workflow_state") or "").strip().lower() != "archived":
            raise HTTPException(
                status_code=409,
                detail="Deze kassabon staat niet in Archief",
            )

        conn.execute(
            legacy_main.text(
                """
                UPDATE receipt_tables
                SET deleted_at = NULL,
                    approved_at = NULL,
                    workflow_state = 'returned_to_kassa',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :receipt_table_id
                  AND household_id = :household_id
                """
            ),
            {
                "receipt_table_id": normalized_receipt_id,
                "household_id": household_id,
            },
        )

        conn.execute(
            legacy_main.text(
                """
                UPDATE purchase_import_batches
                SET import_status = CASE
                        WHEN import_status = 'archived' THEN 'in_review'
                        ELSE import_status
                    END
                WHERE household_id = :household_id
                  AND source_type = 'receipt'
                  AND source_reference = :source_reference
                """
            ),
            {
                "household_id": household_id,
                "source_reference": f"receipt:{normalized_receipt_id}",
            },
        )

    return {
        "status": "ok",
        "receipt_table_id": normalized_receipt_id,
        "workflow_state": "returned_to_kassa",
        "restored_to": "kassa",
    }



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


# Release A must be applied from the actual uvicorn entrypoint. Importing app.main
# from here is deterministic; relying on app.__init__ background threads is not,
# because package initialisation can still be in progress while those threads poll.
install_receipt_lifecycle_foundation(app, legacy_main.engine)

with legacy_main.engine.begin() as provisioning_conn:
    ensure_system_superuser_for_session_runtime(provisioning_conn)
    ensure_authorization_ui_fixture_member(provisioning_conn)
    backfill_membership_user_ids(provisioning_conn)

install_actor_attribution_tracking(legacy_main.engine)
activate_server_side_route_context()
activate_server_side_session_routes()
