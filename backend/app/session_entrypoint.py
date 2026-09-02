"""Rezzerv runtime entrypoint for the server-side session migration.

The existing application remains the single application instance. This module
replaces the legacy authentication endpoints and redirects the central legacy
route guards to the server-side session context. Unrelated routes retain their
existing implementation and order.
"""

from __future__ import annotations

from fastapi import Body, HTTPException, Request
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
import app.main as legacy_main
from app.main import app
from app.api.server_session_routes import create_server_session_router
from app.api.superuser_routes import create_superuser_router
from app.api.superuser_household_routes import create_superuser_household_router
from app.api.support_broadcast_routes import router as support_broadcast_router
from app.services.actor_attribution_service import install_actor_attribution_tracking
from app.services.archived_receipt_purge_route_authorization import (
    archived_receipt_purge_household_context,
    bind_archived_receipt_purge_platform_context,
    required_archived_receipt_purge_permission,
    reset_archived_receipt_purge_platform_context,
)
from app.services.authorization_ui_fixture_provisioning import (
    ensure_authorization_ui_fixture_member,
)
from app.services.external_database_route_authorization import (
    authorize_external_database_request,
    required_external_database_permission,
)
from app.services.external_relation_batch_decision_route_authorization import (
    required_external_relation_batch_decision_permission,
)
from app.services.fixture_lifecycle_route_authorization import (
    required_fixture_lifecycle_permission,
)
from app.services.frontteam_household_provisioning import (
    ensure_frontteam_household_for_session_runtime,
)
from app.services.hybrid_regression_route_authorization import (
    required_hybrid_regression_permissions,
)
from app.services.kassa_diagnostic_route_authorization import (
    required_kassa_diagnostic_permission,
)
from app.services.maintenance_recompute_route_authorization import (
    required_maintenance_recompute_permission,
)
from app.services.membership_user_identity_service import backfill_membership_user_ids
from app.services.receipt_export_fixture_route_authorization import (
    required_receipt_export_fixture_permission,
)
from app.services.receipt_import_batch_runtime_contract import (
    install_receipt_import_batch_runtime_contract,
)
from app.services.receipt_lifecycle_foundation_service import (
    apply_unpack_receipt_lifecycle_action,
    install_receipt_lifecycle_foundation,
    resolve_receipt_for_unpack_batch,
)
from app.services.purchase_import_batch_diagnostics_route_authorization import (
    required_purchase_import_batch_diagnostics_permission,
)
from app.services.receipt_status_baseline_route_authorization import (
    required_receipt_status_baseline_permissions,
)
from app.services.session_request_context import (
    authorized_household_id_from_session,
    bind_current_actor_from_request_session_if_available,
    bind_request_session,
    household_context_from_session,
    legacy_household_context_from_session,
    legacy_user_payload_from_session,
    request_household_id_from_session,
    require_household_admin_from_session,
    require_platform_permission_from_session,
    require_platform_permissions_from_session,
    reset_request_session,
    resolve_current_server_session,
)
from app.services.support_message_session_adapter import household_support_actor
from app.services.system_superuser_session_provisioning import (
    ensure_system_superuser_for_session_runtime,
)
from app.services.testing_status_route_authorization import (
    required_testing_status_permission,
)


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


def require_household_admin_with_platform_recovery(
    authorization: str | None = None,
    requested_household_id: str | None = None,
) -> dict:
    """Keep household-admin semantics except for the authorized purge route."""

    recovery_context = archived_receipt_purge_household_context(requested_household_id)
    if recovery_context is not None:
        return recovery_context
    return require_household_admin_from_session(
        authorization,
        requested_household_id,
    )


def activate_server_side_route_context() -> None:
    """Make the server session the sole authority for existing route guards."""

    legacy_main.get_current_user_from_authorization = legacy_user_payload_from_session
    legacy_main.resolve_household_context_for_user = legacy_household_context_from_session
    legacy_main.require_household_context = household_context_from_session
    legacy_main.require_household_admin_context = require_household_admin_with_platform_recovery
    legacy_main.resolve_authorized_household_id = authorized_household_id_from_session
    legacy_main.get_request_household_id = request_household_id_from_session

    # The existing support-message router originally admitted only household
    # administrators. Rezzerv's functional contract allows every authenticated
    # active household member to contact the superuser and continue that
    # conversation. Platform support routes keep their platform permission gate.
    from app.api import support_message_routes
    support_message_routes._household_actor = household_support_actor


@app.middleware("http")
async def server_session_request_context(request: Request, call_next):
    token = bind_request_session(request)
    archived_receipt_purge_context_token = None
    try:
        # Bind the canonical actor before any route/service can write domain data.
        # Public requests without a valid server session remain unattributed.
        current_context = bind_current_actor_from_request_session_if_available()

        fixture_permission = (
            required_receipt_export_fixture_permission(
                request.method,
                request.url.path,
            )
            or required_fixture_lifecycle_permission(
                request.method,
                request.url.path,
            )
        )
        if fixture_permission is not None:
            require_platform_permission_from_session(
                fixture_permission,
                request.headers.get("authorization"),
            )

        testing_status_permission = required_testing_status_permission(
            request.method,
            request.url.path,
        )
        if testing_status_permission is not None:
            require_platform_permission_from_session(
                testing_status_permission,
                request.headers.get("authorization"),
            )

        purchase_import_batch_diagnostics_permission = (
            required_purchase_import_batch_diagnostics_permission(
                request.method,
                request.url.path,
            )
        )
        if purchase_import_batch_diagnostics_permission is not None:
            require_platform_permission_from_session(
                purchase_import_batch_diagnostics_permission,
                request.headers.get("authorization"),
            )

        hybrid_regression_permissions = required_hybrid_regression_permissions(
            request.method,
            request.url.path,
        )
        if hybrid_regression_permissions:
            require_platform_permissions_from_session(
                hybrid_regression_permissions,
                request.headers.get("authorization"),
            )

        kassa_permission = required_kassa_diagnostic_permission(
            request.method,
            request.url.path,
        )
        if kassa_permission is not None:
            require_platform_permission_from_session(
                kassa_permission,
                request.headers.get("authorization"),
            )

        maintenance_recompute_permission = required_maintenance_recompute_permission(
            request.method,
            request.url.path,
        )
        if maintenance_recompute_permission is not None:
            require_platform_permission_from_session(
                maintenance_recompute_permission,
                request.headers.get("authorization"),
            )

        receipt_status_baseline_permissions = required_receipt_status_baseline_permissions(
            request.method,
            request.url.path,
        )
        if receipt_status_baseline_permissions:
            require_platform_permissions_from_session(
                receipt_status_baseline_permissions,
                request.headers.get("authorization"),
            )

        archived_receipt_purge_permission = required_archived_receipt_purge_permission(
            request.method,
            request.url.path,
        )
        if archived_receipt_purge_permission is not None:
            purge_context = require_platform_permission_from_session(
                archived_receipt_purge_permission,
                request.headers.get("authorization"),
            )
            archived_receipt_purge_context_token = bind_archived_receipt_purge_platform_context(
                purge_context
            )

        external_relation_batch_decision_permission = required_external_relation_batch_decision_permission(
            request.method,
            request.url.path,
        )
        if external_relation_batch_decision_permission is not None:
            require_platform_permission_from_session(
                external_relation_batch_decision_permission,
                request.headers.get("authorization"),
            )

        # External database routes used to rely only on frontend navigation.
        # Enforce the platform permission matrix server-side for every request.
        required_permission = required_external_database_permission(
            request.method,
            request.url.path,
        )
        if required_permission is not None:
            context = current_context or resolve_current_server_session()
            with legacy_main.engine.begin() as conn:
                authorize_external_database_request(
                    conn,
                    user_id=context.user_id,
                    method=request.method,
                    path=request.url.path,
                )

        return await call_next(request)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )
    finally:
        if archived_receipt_purge_context_token is not None:
            reset_archived_receipt_purge_platform_context(
                archived_receipt_purge_context_token
            )
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
install_receipt_import_batch_runtime_contract(legacy_main)
install_receipt_lifecycle_foundation(app, legacy_main.engine)

with legacy_main.engine.begin() as provisioning_conn:
    ensure_system_superuser_for_session_runtime(provisioning_conn)
    ensure_frontteam_household_for_session_runtime(provisioning_conn)
    ensure_authorization_ui_fixture_member(provisioning_conn)
    backfill_membership_user_ids(provisioning_conn)

install_actor_attribution_tracking(legacy_main.engine)
activate_server_side_route_context()
activate_server_side_session_routes()
