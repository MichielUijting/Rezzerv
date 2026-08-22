from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.services.platform_admin_route_guard import (
    PROTECTED_MUTATIONS,
    RECEIPT_EXPORT_FIXTURE_PERMISSION,
    RECEIPT_EXPORT_FIXTURE_ROUTES,
    authorize_platform_admin_request,
    authorize_receipt_export_fixture_request,
    deduplicate_receipt_parser_diagnosis_routes,
    install_platform_admin_route_guard,
)

EXPECTED_PROTECTED_MUTATIONS = {
    ("POST", "/api/testing/diagnostics/store-location-options"),
    ("POST", "/api/testing/fixtures/browser-regression/reset"),
    ("POST", "/api/testing/fixtures/cleanup"),
    ("POST", "/api/testing/fixtures/inventory/ensure"),
    ("POST", "/api/testing/fixtures/receipt-layer1/generate"),
    ("POST", "/api/testing/fixtures/receipts/seed-kassa"),
    ("POST", "/api/testing/regression/almost-out-prediction"),
    ("POST", "/api/testing/regression/almost-out-self-test"),
    ("POST", "/api/admin/backfill-purchase-import-live-aliases"),
    ("POST", "/api/admin/diagnose-receipt-status-baseline"),
    ("POST", "/api/admin/external-relations/batch/decision"),
    ("POST", "/api/admin/kassa-regression/run"),
    ("POST", "/api/admin/kassa-smoke/run"),
    ("POST", "/api/admin/product-groups/import-gpc-nl"),
    ("POST", "/api/admin/receipts/purge-archived"),
    ("POST", "/api/admin/recompute-receipt-statuses"),
    ("POST", "/api/admin/validate-receipt-status-baseline"),
}

EXPECTED_RECEIPT_EXPORT_FIXTURE_ROUTES = {
    ("POST", "/api/testing/fixtures/receipt-export/generate"),
    ("GET", "/api/testing/fixtures/receipt-export/download"),
}


def run_contract() -> None:
    assert PROTECTED_MUTATIONS == EXPECTED_PROTECTED_MUTATIONS
    assert len(PROTECTED_MUTATIONS) == 17
    assert ("POST", "/api/admin/inventory/groups/ensure-schema") not in PROTECTED_MUTATIONS
    assert ("POST", "/api/testing/fixtures/receipt-export/generate") not in PROTECTED_MUTATIONS
    assert RECEIPT_EXPORT_FIXTURE_ROUTES == EXPECTED_RECEIPT_EXPORT_FIXTURE_ROUTES
    assert RECEIPT_EXPORT_FIXTURE_PERMISSION == "platform.test_fixtures.manage"

    permission_calls: list[tuple[str, str | None]] = []

    def require_platform_permission(permission_key: str, authorization: str | None):
        permission_calls.append((permission_key, authorization))
        if authorization != "Bearer fixture-admin":
            raise HTTPException(status_code=403, detail="Fixturebeheer vereist")
        return {"permission": permission_key}

    for method, path in sorted(RECEIPT_EXPORT_FIXTURE_ROUTES):
        permission_calls.clear()
        try:
            authorize_receipt_export_fixture_request(
                method,
                path,
                "Bearer household-user",
                require_platform_permission,
            )
        except HTTPException as exc:
            assert exc.status_code == 403
        else:
            raise AssertionError(f"{method} {path} had moeten worden geweigerd")
        assert permission_calls == [
            (RECEIPT_EXPORT_FIXTURE_PERMISSION, "Bearer household-user")
        ]

        permission_calls.clear()
        allowed = authorize_receipt_export_fixture_request(
            method,
            path,
            "Bearer fixture-admin",
            require_platform_permission,
        )
        assert allowed == {"permission": RECEIPT_EXPORT_FIXTURE_PERMISSION}
        assert permission_calls == [
            (RECEIPT_EXPORT_FIXTURE_PERMISSION, "Bearer fixture-admin")
        ]

    assert authorize_receipt_export_fixture_request(
        "GET",
        "/api/testing/reports/complete",
        None,
        require_platform_permission,
    ) is None

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

    print("PLATFORM_ADMIN_ROUTE_GUARD_GREEN")


if __name__ == "__main__":
    run_contract()
