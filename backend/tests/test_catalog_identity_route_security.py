"""API authorization, receipt ownership and write gating for store-code confirmation.

Exercises the actual FastAPI route through HTTP (not just its domain service).
All database interactions are isolated fakes; no user records are touched.
"""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import barcode_routes as routes


class SourceResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class Conn:
    def __init__(self, owner="h1", code="0082346", retailer="Lidl"):
        self.owner = owner
        self.code = code
        self.retailer = retailer
        self.queries = []

    def execute(self, statement, params):
        self.queries.append((str(statement), dict(params)))
        # The authorization SELECT must use the authenticated household.
        if params["household"] != self.owner or params["line"] != "line-one":
            return SourceResult(None)
        return SourceResult({"retailer": self.retailer, "article_code": self.code})


@pytest.fixture
def endpoint(monkeypatch):
    connection = Conn()
    confirmation = Mock(return_value={
        "status": "confirmed", "global_product_id": "p1", "changes": 1,
    })
    repair = Mock(return_value={"status": "linked", "updated": 1})
    context = {"user_id": "member-1", "active_household_id": "h1", "role": "owner"}
    permit = Mock()
    monkeypatch.setattr(routes, "_require_authenticated_context", lambda authorization: context)
    monkeypatch.setattr(routes, "require_platform_permission_from_session", permit)
    monkeypatch.setattr(routes, "household_context_from_runtime_context", lambda _: SimpleNamespace(
        active_household_id=context["active_household_id"], role=context["role"],
    ))
    monkeypatch.setattr(routes, "engine", SimpleNamespace(begin=lambda: nullcontext(connection)))
    monkeypatch.setattr(routes, "confirm_scanned_retailer_identity", confirmation)
    monkeypatch.setattr(routes, "repair_household_articles_for_confirmed_store_code", repair)
    # begin_nested is a PostgreSQL savepoint in production; use a harmless
    # context manager in the transport test.
    connection.begin_nested = lambda: nullcontext()
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app), context, connection, confirmation, repair, permit


def payload(**overrides):
    return {
        "receipt_item_id": "receipt-table-line:line-one",
        "retailer_code": "lidl", "external_article_code": "0082346",
        "gtin": "8712345678906", **overrides,
    }


def test_valid_member_confirms_exact_owned_receipt_and_is_household_scoped(endpoint):
    client, context, conn, confirm, repair, permit = endpoint
    result = client.post("/api/barcodes/confirm-retailer-code", json=payload())
    assert result.status_code == 200, result.text
    assert result.json()["historical_repair"]["updated"] == 1
    permit.assert_called_once_with("platform.external_products.link_existing")
    assert conn.queries and conn.queries[0][1] == {
        "line": "line-one", "household": "h1",
    }
    assert "rt.household_id = :household" in conn.queries[0][0]
    assert confirm.call_args.kwargs["confirmed_by"] == "member-1"
    assert repair.call_args.kwargs["household_id"] == "h1"
    assert repair.call_args.kwargs["global_product_id"] == "p1"


def test_missing_session_is_401_and_never_writes(endpoint, monkeypatch):
    client, context, conn, confirm, repair, permit = endpoint
    def no_session(_authorization):
        raise HTTPException(status_code=401, detail="Geldige sessie vereist")
    monkeypatch.setattr(routes, "_require_authenticated_context", no_session)
    response = client.post("/api/barcodes/confirm-retailer-code", json=payload())
    assert response.status_code == 401
    assert not conn.queries
    confirm.assert_not_called()
    repair.assert_not_called()


def test_missing_platform_permission_is_403_and_never_writes(endpoint):
    client, context, conn, confirm, repair, permit = endpoint
    permit.side_effect = HTTPException(status_code=403, detail="Geen platformrecht")
    response = client.post("/api/barcodes/confirm-retailer-code", json=payload())
    assert response.status_code == 403
    assert not conn.queries
    confirm.assert_not_called()


def test_viewer_cannot_confirm_even_with_platform_permission(endpoint):
    client, context, conn, confirm, repair, permit = endpoint
    context["role"] = "viewer"
    response = client.post("/api/barcodes/confirm-retailer-code", json=payload())
    assert response.status_code == 403
    assert not conn.queries
    confirm.assert_not_called()


def test_foreign_household_receipt_is_404_and_never_writes(endpoint):
    client, context, conn, confirm, repair, permit = endpoint
    context["active_household_id"] = "h2"
    response = client.post("/api/barcodes/confirm-retailer-code", json=payload())
    assert response.status_code == 404
    assert conn.queries[0][1]["household"] == "h2"
    confirm.assert_not_called()
    repair.assert_not_called()


@pytest.mark.parametrize("overrides,status", [
    ({"external_article_code": "not-on-receipt"}, 409),
    ({"retailer_code": "jumbo"}, 409),
    ({"receipt_item_id": "purchase-import-line:line-one"}, 422),
    ({"receipt_item_id": "receipt-table-line:"}, 422),
    ({"gtin": ""}, 422),
])
def test_invalid_identity_cannot_write(endpoint, overrides, status):
    client, context, conn, confirm, repair, permit = endpoint
    response = client.post("/api/barcodes/confirm-retailer-code", json=payload(**overrides))
    assert response.status_code == status, response.text
    confirm.assert_not_called()
    repair.assert_not_called()


def test_historical_repair_failure_preserves_confirmed_identity_but_reports_deferred(endpoint):
    client, context, conn, confirm, repair, permit = endpoint
    repair.side_effect = ValueError("Onvolledige bron")
    response = client.post("/api/barcodes/confirm-retailer-code", json=payload())
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert response.json()["historical_repair"] == {"updated": 0, "status": "deferred"}
    confirm.assert_called_once()
