from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.services.product_enrichment_write_guard import (
    authorize_product_enrichment_request,
    extract_requested_household_id,
    install_product_enrichment_write_guard,
)


def run_contract() -> None:
    app = FastAPI()
    calls: list[str] = []

    def require_inventory_write_context(authorization: str | None, requested_household_id: str | None):
        if not authorization:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if authorization == "Bearer viewer":
            raise HTTPException(status_code=403, detail="Kijkers mogen deze voorraadactie niet uitvoeren")
        if authorization != "Bearer writer":
            raise HTTPException(status_code=403, detail="Geen toegang")
        if requested_household_id not in {None, "household-a"}:
            raise HTTPException(status_code=403, detail="Geen toegang")
        return {"active_household_id": "household-a", "display_role": "lid"}

    install_product_enrichment_write_guard(
        SimpleNamespace(
            app=app,
            require_inventory_write_context=require_inventory_write_context,
        )
    )

    @app.post("/api/products/enrich")
    def enrich():
        calls.append("enrich")
        return {"status": "ok"}

    @app.post("/api/products/enrich/retry")
    def retry():
        calls.append("retry")
        return {"status": "ok"}

    @app.post("/api/products/identify")
    def identify():
        calls.append("identify")
        return {"status": "ok"}

    client = TestClient(app)
    payload = {"household_id": "household-a", "article_name": "Melk", "force_refresh": False}

    response = client.post("/api/products/enrich", json=payload)
    assert response.status_code == 401, response.text
    assert calls == []

    response = client.post(
        "/api/products/enrich",
        json=payload,
        headers={"Authorization": "Bearer viewer"},
    )
    assert response.status_code == 403, response.text
    assert calls == []

    response = client.post(
        "/api/products/enrich",
        json={**payload, "household_id": "household-b"},
        headers={"Authorization": "Bearer writer"},
    )
    assert response.status_code == 403, response.text
    assert calls == []

    response = client.post(
        "/api/products/enrich",
        json=payload,
        headers={"Authorization": "Bearer writer"},
    )
    assert response.status_code == 200, response.text
    assert calls == ["enrich"]

    response = client.post(
        "/api/products/enrich/retry",
        json=payload,
        headers={"Authorization": "Bearer viewer"},
    )
    assert response.status_code == 403, response.text
    assert calls == ["enrich"]

    response = client.post(
        "/api/products/enrich/retry",
        json=payload,
        headers={"Authorization": "Bearer writer"},
    )
    assert response.status_code == 200, response.text
    assert calls == ["enrich", "retry"]

    response = client.post("/api/products/identify")
    assert response.status_code == 200, response.text
    assert calls == ["enrich", "retry", "identify"]

    assert extract_requested_household_id(b'{"household_id":"household-a"}') == "household-a"
    assert extract_requested_household_id(b'{}') is None
    assert extract_requested_household_id(b'not-json') is None

    assert authorize_product_enrichment_request(
        "GET",
        "/api/products/enrich",
        None,
        b"",
        require_inventory_write_context,
    ) is None
    assert authorize_product_enrichment_request(
        "POST",
        "/api/products/identify",
        None,
        b"",
        require_inventory_write_context,
    ) is None

    print("PRODUCT_ENRICHMENT_WRITE_GUARD_GREEN")


if __name__ == "__main__":
    run_contract()
