from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Header
from fastapi.testclient import TestClient

from app.services.receipt_admin_household_guard import (
    authorize_receipt_admin_request,
    install_receipt_admin_household_guard,
)


def run_contract() -> None:
    app = FastAPI()
    calls: list[str] = []

    def require_platform_admin_user(authorization: str | None):
        if not authorization:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if authorization != "Bearer platform-admin":
            raise HTTPException(status_code=403, detail="Platformbeheerder vereist")
        return {"email": "platform@example.test", "role": "platform_admin"}

    install_receipt_admin_household_guard(
        SimpleNamespace(app=app, require_platform_admin_user=require_platform_admin_user)
    )

    protected_routes = [
        ("post", "/api/admin/backfill-purchase-import-live-aliases", "live-alias-backfill"),
        ("post", "/api/admin/recompute-receipt-statuses", "recompute"),
        ("post", "/api/admin/validate-receipt-status-baseline", "validate"),
        ("post", "/api/admin/diagnose-receipt-status-baseline", "diagnose"),
        ("post", "/api/testing/fixtures/receipt-export/generate", "fixture-generate"),
        ("get", "/api/testing/fixtures/receipt-export/download", "fixture-download"),
        ("post", "/api/testing/diagnostics/store-location-options", "store-location-diagnostic"),
        ("post", "/api/testing/regression/almost-out-prediction", "almost-out-prediction"),
        ("post", "/api/testing/regression/almost-out-self-test", "almost-out-self-test"),
        ("post", "/api/testing/fixtures/inventory/ensure", "inventory-fixture-ensure"),
    ]

    def register(method: str, path: str, marker: str) -> None:
        def endpoint():
            calls.append(marker)
            return {"status": "ok", "marker": marker}

        app.add_api_route(path, endpoint, methods=[method.upper()])

    for method, path, marker in protected_routes:
        register(method, path, marker)

    @app.get("/api/testing/diagnostics/store-process-validation")
    def unrelated_testing_diagnostic():
        calls.append("unrelated-testing")
        return {"status": "ok"}

    @app.post("/api/admin/unrelated")
    def unrelated_admin_route(authorization: str | None = Header(None)):
        calls.append("unrelated")
        return {"status": "ok", "authorization": authorization}

    with TestClient(app) as client:
        for method, path, marker in protected_routes:
            before = list(calls)
            response = client.request(method.upper(), path)
            assert response.status_code == 401, (path, response.text)
            assert calls == before, f"{marker} werd ondanks 401 uitgevoerd"

            response = client.request(
                method.upper(),
                path,
                headers={"Authorization": "Bearer household-user"},
            )
            assert response.status_code == 403, (path, response.text)
            assert calls == before, f"{marker} werd ondanks 403 uitgevoerd"

            response = client.request(
                method.upper(),
                path,
                headers={"Authorization": "Bearer platform-admin"},
            )
            assert response.status_code == 200, (path, response.text)
            assert calls[-1] == marker

        response = client.get("/api/testing/diagnostics/store-process-validation")
        assert response.status_code == 200, response.text
        assert calls[-1] == "unrelated-testing"

        response = client.post("/api/admin/unrelated")
        assert response.status_code == 200, response.text
        assert calls[-1] == "unrelated"

    assert authorize_receipt_admin_request(
        "GET",
        "/api/testing/regression/almost-out-prediction",
        None,
        require_platform_admin_user,
    ) is None
    assert authorize_receipt_admin_request(
        "GET",
        "/api/testing/fixtures/inventory/ensure",
        None,
        require_platform_admin_user,
    ) is None

    print("RECEIPT_ADMIN_HOUSEHOLD_GUARD_GREEN")


if __name__ == "__main__":
    run_contract()
