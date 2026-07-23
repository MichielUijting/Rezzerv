from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.testclient import TestClient

from app.services.receipt_gmail_oauth_household_guard import (
    install_receipt_gmail_oauth_household_guard,
)


def run_contract() -> None:
    app = FastAPI()
    calls = {"connect": 0, "callback": 0, "other": 0}

    def require_household_admin_context(authorization: str | None, household_id: str | None):
        if not authorization:
            raise HTTPException(status_code=401, detail="Autorisatie ontbreekt")
        if authorization == "Bearer member-a":
            raise HTTPException(status_code=403, detail="Huishoudadmin vereist")
        if authorization != "Bearer admin-a" or household_id != "household-a":
            raise HTTPException(status_code=403, detail="Geen toegang tot dit huishouden")
        return {"active_household_id": "household-a", "display_role": "admin"}

    def verify_gmail_state(state: str):
        states = {
            "valid": {"provider": "gmail", "household_id": "household-a"},
            "missing-household": {"provider": "gmail"},
            "wrong-provider": {"provider": "other", "household_id": "household-a"},
        }
        payload = states.get(state)
        if payload is None:
            raise HTTPException(status_code=400, detail="Ongeldige OAuth-state")
        return payload

    main_module = SimpleNamespace(
        app=app,
        require_household_admin_context=require_household_admin_context,
        verify_gmail_state=verify_gmail_state,
    )
    install_receipt_gmail_oauth_household_guard(main_module)

    @app.get("/api/receipts/gmail/connect-url")
    def connect_url(
        householdId: str = Query(...),
        authorization: str | None = Header(None),
    ):
        calls["connect"] += 1
        return {"household_id": householdId, "authorization": authorization}

    @app.get("/api/receipts/gmail/callback")
    def callback(state: str = Query(...)):
        calls["callback"] += 1
        return {"state": state}

    @app.get("/api/receipts/gmail/status-probe")
    def other_route():
        calls["other"] += 1
        return {"ok": True}

    client = TestClient(app)

    response = client.get("/api/receipts/gmail/connect-url?householdId=household-a")
    assert response.status_code == 401, response.text
    assert calls["connect"] == 0

    response = client.get(
        "/api/receipts/gmail/connect-url?householdId=household-a",
        headers={"Authorization": "Bearer member-a"},
    )
    assert response.status_code == 403, response.text
    assert calls["connect"] == 0

    response = client.get(
        "/api/receipts/gmail/connect-url?householdId=household-b",
        headers={"Authorization": "Bearer admin-a"},
    )
    assert response.status_code == 403, response.text
    assert calls["connect"] == 0

    response = client.get(
        "/api/receipts/gmail/connect-url?householdId=household-a",
        headers={"Authorization": "Bearer admin-a"},
    )
    assert response.status_code == 200, response.text
    assert calls["connect"] == 1

    response = client.get("/api/receipts/gmail/callback?state=missing-household")
    assert response.status_code == 400, response.text
    assert calls["callback"] == 0

    response = client.get("/api/receipts/gmail/callback?state=wrong-provider")
    assert response.status_code == 400, response.text
    assert calls["callback"] == 0

    response = client.get("/api/receipts/gmail/callback?state=unknown")
    assert response.status_code == 400, response.text
    assert calls["callback"] == 0

    response = client.get("/api/receipts/gmail/callback?state=valid")
    assert response.status_code == 200, response.text
    assert calls["callback"] == 1

    response = client.get("/api/receipts/gmail/status-probe")
    assert response.status_code == 200, response.text
    assert calls["other"] == 1


if __name__ == "__main__":
    run_contract()
    print("receipt Gmail OAuth household guard contract: OK")
