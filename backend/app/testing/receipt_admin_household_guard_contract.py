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

    module = SimpleNamespace(
        app=app,
        require_platform_admin_user=require_platform_admin_user,
    )
    install_receipt_admin_household_guard(module)

    @app.post("/api/admin/recompute-receipt-statuses")
    def recompute_receipt_statuses(authorization: str | None = Header(None)):
        calls.append("recompute")
        return {"status": "ok", "authorization": authorization}

    @app.post("/api/admin/validate-receipt-status-baseline")
    def validate_receipt_status_baseline():
        calls.append("validate")
        return {"status": "ok"}

    @app.post("/api/admin/diagnose-receipt-status-baseline")
    def diagnose_receipt_status_baseline():
        calls.append("diagnose")
        return {"status": "ok"}

    @app.post("/api/admin/unrelated")
    def unrelated_admin_route():
        calls.append("unrelated")
        return {"status": "ok"}

    client = TestClient(app)

    response = client.post("/api/admin/recompute-receipt-statuses")
    assert response.status_code == 401, response.text
    assert calls == []

    response = client.post(
        "/api/admin/validate-receipt-status-baseline",
        headers={"Authorization": "Bearer household-user"},
    )
    assert response.status_code == 403, response.text
    assert calls == []

    response = client.post(
        "/api/admin/diagnose-receipt-status-baseline",
        headers={"Authorization": "Bearer platform-admin"},
    )
    assert response.status_code == 200, response.text
    assert calls == ["diagnose"]

    response = client.post("/api/admin/unrelated")
    assert response.status_code == 200, response.text
    assert calls == ["diagnose", "unrelated"]

    assert authorize_receipt_admin_request(
        "GET",
        "/api/admin/recompute-receipt-statuses",
        None,
        require_platform_admin_user,
    ) is None

    print("RECEIPT_ADMIN_HOUSEHOLD_GUARD_GREEN")


if __name__ == "__main__":
    run_contract()
