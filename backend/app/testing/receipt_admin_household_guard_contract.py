from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.services.platform_admin_route_guard import (
    PROTECTED_MUTATIONS,
    authorize_platform_admin_request,
    deduplicate_receipt_parser_diagnosis_routes,
    install_platform_admin_route_guard,
)

EXPECTED_PROTECTED_MUTATIONS: set[tuple[str, str]] = set()

MIGRATED_TEST_MUTATIONS = {
    ("POST", "/api/testing/diagnostics/store-location-options"),
    ("POST", "/api/testing/fixtures/browser-regression/reset"),
    ("POST", "/api/testing/fixtures/cleanup"),
    ("POST", "/api/testing/fixtures/inventory/ensure"),
    ("POST", "/api/testing/fixtures/receipt-export/generate"),
    ("POST", "/api/testing/fixtures/receipt-layer1/generate"),
    ("POST", "/api/testing/fixtures/receipts/seed-kassa"),
    ("POST", "/api/testing/regression/almost-out-prediction"),
    ("POST", "/api/testing/regression/almost-out-self-test"),
}

MIGRATED_KASSA_DIAGNOSTIC_MUTATIONS = {
    ("POST", "/api/admin/kassa-regression/run"),
    ("POST", "/api/admin/kassa-smoke/run"),
}

MIGRATED_MAINTENANCE_RECOMPUTE_MUTATIONS = {
    ("POST", "/api/admin/backfill-purchase-import-live-aliases"),
    ("POST", "/api/admin/recompute-receipt-statuses"),
}

MIGRATED_RECEIPT_STATUS_BASELINE_MUTATIONS = {
    ("POST", "/api/admin/diagnose-receipt-status-baseline"),
    ("POST", "/api/admin/validate-receipt-status-baseline"),
}

MIGRATED_GPC_NL_IMPORT_MUTATIONS = {
    ("POST", "/api/admin/product-groups/import-gpc-nl"),
}

MIGRATED_ARCHIVED_RECEIPT_PURGE_MUTATIONS = {
    ("POST", "/api/admin/receipts/purge-archived"),
}

MIGRATED_EXTERNAL_RELATION_BATCH_DECISION_MUTATIONS = {
    ("POST", "/api/admin/external-relations/batch/decision"),
}


def run_contract() -> None:
    assert PROTECTED_MUTATIONS == EXPECTED_PROTECTED_MUTATIONS
    assert len(PROTECTED_MUTATIONS) == 0
    assert ("POST", "/api/admin/inventory/groups/ensure-schema") not in PROTECTED_MUTATIONS
    assert PROTECTED_MUTATIONS.isdisjoint(MIGRATED_TEST_MUTATIONS)
    assert PROTECTED_MUTATIONS.isdisjoint(MIGRATED_KASSA_DIAGNOSTIC_MUTATIONS)
    assert PROTECTED_MUTATIONS.isdisjoint(MIGRATED_MAINTENANCE_RECOMPUTE_MUTATIONS)
    assert PROTECTED_MUTATIONS.isdisjoint(MIGRATED_RECEIPT_STATUS_BASELINE_MUTATIONS)
    assert PROTECTED_MUTATIONS.isdisjoint(MIGRATED_GPC_NL_IMPORT_MUTATIONS)
    assert PROTECTED_MUTATIONS.isdisjoint(MIGRATED_ARCHIVED_RECEIPT_PURGE_MUTATIONS)
    assert PROTECTED_MUTATIONS.isdisjoint(MIGRATED_EXTERNAL_RELATION_BATCH_DECISION_MUTATIONS)

    app = FastAPI()
    calls: list[str] = []

    def require_platform_admin_user(authorization: str | None):
        if not authorization:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if authorization != "Bearer platform-admin":
            raise HTTPException(status_code=403, detail="Platformbeheerder vereist")
        return {"role": "platform_admin"}

    for method, path in sorted(PROTECTED_MUTATIONS):
        marker = f"{method} {path}"

        def endpoint(marker=marker):
            calls.append(marker)
            return {"status": "ok", "marker": marker}

        app.add_api_route(path, endpoint, methods=[method])

    @app.get("/api/testing/receipt-parser-diagnosis")
    def preferred_diagnosis():
        return {"source": "preferred"}

    preferred_diagnosis.__module__ = "app.api.receipt_diagnosis_routes"

    @app.get("/api/testing/receipt-parser-diagnosis")
    def duplicate_diagnosis():
        return {"source": "duplicate"}

    duplicate_diagnosis.__module__ = "app.api.routes.receipt_parser_diagnosis"

    removed = deduplicate_receipt_parser_diagnosis_routes(app)
    assert removed == 1
    matching = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/testing/receipt-parser-diagnosis"
    ]
    assert len(matching) == 1
    assert matching[0].endpoint.__module__ == "app.api.receipt_diagnosis_routes"

    install_platform_admin_route_guard(
        SimpleNamespace(app=app, require_platform_admin_user=require_platform_admin_user)
    )

    with TestClient(app) as client:
        for method, path in sorted(PROTECTED_MUTATIONS):
            before = list(calls)
            response = client.request(method, path)
            assert response.status_code == 401, (method, path, response.text)
            assert calls == before

            response = client.request(
                method,
                path,
                headers={"Authorization": "Bearer household-user"},
            )
            assert response.status_code == 403, (method, path, response.text)
            assert calls == before

            response = client.request(
                method,
                path,
                headers={"Authorization": "Bearer platform-admin"},
            )
            assert response.status_code == 200, (method, path, response.text)
            assert calls[-1] == f"{method} {path}"

    assert authorize_platform_admin_request(
        "GET",
        "/api/testing/reports/complete",
        None,
        require_platform_admin_user,
    ) is None

    assert authorize_platform_admin_request(
        "POST",
        "/api/admin/external-relations/batch/decision",
        "Bearer platform-admin",
        require_platform_admin_user,
    ) is None

    print("PLATFORM_ADMIN_ROUTE_GUARD_GREEN")


if __name__ == "__main__":
    run_contract()
