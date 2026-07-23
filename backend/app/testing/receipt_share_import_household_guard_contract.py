"""HTTP contract for authenticated household-scoped receipt share import."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.services.receipt_share_import_household_guard import (
    install_receipt_share_import_household_guard,
)


def run_contract() -> None:
    app = FastAPI()
    endpoint_calls: list[str] = []

    @app.post("/api/receipts/share-import")
    async def share_import_endpoint(
        household_id: str = Form(...),
        file: UploadFile = File(...),
    ):
        endpoint_calls.append(household_id)
        return {
            "household_id": household_id,
            "filename": file.filename,
        }

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    def require_household_context(authorization, requested_household_id):
        token_household = {
            "Bearer token-a": "household-a",
            "Bearer token-b": "household-b",
        }.get(authorization)
        if token_household is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if token_household != requested_household_id:
            raise HTTPException(status_code=403, detail="Geen toegang")
        return {
            "active_household_id": token_household,
            "display_role": "admin",
        }

    install_receipt_share_import_household_guard(
        SimpleNamespace(
            app=app,
            require_household_context=require_household_context,
        )
    )
    client = TestClient(app)

    def post_share(household_id: str | None, authorization: str | None = None):
        data = {} if household_id is None else {"household_id": household_id}
        headers = {} if authorization is None else {"Authorization": authorization}
        return client.post(
            "/api/receipts/share-import",
            data=data,
            files={"file": ("receipt.jpg", b"receipt", "image/jpeg")},
            headers=headers,
        )

    response = post_share("household-a")
    assert response.status_code == 401, response.text
    assert endpoint_calls == []

    response = post_share("household-b", "Bearer token-a")
    assert response.status_code == 403, response.text
    assert endpoint_calls == []

    response = post_share(None, "Bearer token-a")
    assert response.status_code == 400, response.text
    assert endpoint_calls == []

    response = post_share("household-a", "Bearer token-a")
    assert response.status_code == 200, response.text
    assert response.json()["household_id"] == "household-a"
    assert endpoint_calls == ["household-a"]

    response = client.get("/api/health")
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}

    print("RECEIPT_SHARE_IMPORT_HOUSEHOLD_GUARD_GREEN")


if __name__ == "__main__":
    run_contract()
