"""Read-only CBS selection contract without changing normal test database authority."""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import cbs_classification_routes as routes
from app.services.classification_server_paging_service import load_selected_cbs_snapshots


PRODUCTS = {
    "first": {"id": "first", "name": "Halfvolle melk", "version": 0,
              "classified": False, "deleted": False},
    "second": {"id": "second", "name": "Volle melk", "version": 3,
               "classified": True, "deleted": False},
    "inactive": {"id": "inactive", "name": "Eerder geclassificeerd", "version": 7,
                 "classified": False, "deleted": False},
    "deleted": {"id": "deleted", "name": "Verwijderd", "version": 2,
                "classified": True, "deleted": True},
}


class SelectionConnection:
    """Validates the parameterized SELECT contract; never connects to runtime data."""
    def __init__(self):
        self.statements = []

    def execute(self, statement, params):
        sql = str(statement)
        self.statements.append(sql)
        assert "FROM global_products gp" in sql
        assert "LEFT JOIN global_product_cbs_classifications cc" in sql
        assert "LOWER(COALESCE(gp.status, '')) <> 'deleted'" in sql
        assert statement._bindparams["product_ids"].expanding is True
        selected = params["product_ids"]
        # Simulate database order different from user selection; the service
        # must still return every requested exact product in input order.
        rows = [
            {"id": row["id"], "name": row["name"], "version": row["version"],
             "is_active": row["classified"]}
            for key, row in sorted(PRODUCTS.items())
            if key in selected and not row["deleted"]
        ]
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))


class SelectionEngine:
    def __init__(self):
        self.connection = SelectionConnection()

    def connect(self):
        return nullcontext(self.connection)


def test_selected_snapshots_preserve_exact_identity_order_and_inactive_version():
    conn = SelectionConnection()
    result = load_selected_cbs_snapshots(conn, ["inactive", "first", "second"])
    assert result == {"total": 3, "items": [
        {"id": "inactive", "name": "Eerder geclassificeerd", "version": 7, "classified": False},
        {"id": "first", "name": "Halfvolle melk", "version": 0, "classified": False},
        {"id": "second", "name": "Volle melk", "version": 3, "classified": True},
    ]}
    assert len(conn.statements) == 1


@pytest.mark.parametrize("ids", [
    [], ["first", "first"], ["deleted"], ["missing"], ["first"] * 101, [""], ["x" * 201],
])
def test_incomplete_duplicate_deleted_and_oversized_selection_fails_closed(ids):
    with pytest.raises(ValueError):
        load_selected_cbs_snapshots(SelectionConnection(), ids)


def test_api_requires_canonical_platform_actor_and_rejects_invalid_payload(monkeypatch):
    fake = SelectionEngine()
    monkeypatch.setattr(routes, "engine", fake)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)

    def actor(superuser=False, frontteam=False, context="regular"):
        return SimpleNamespace(is_platform_superuser=superuser, is_frontteam=frontteam,
                               context_type=context, user_id="member")
    target = "/api/cbs-classifications/workqueue-selected-cbs-snapshots"

    monkeypatch.setattr(routes, "require_platform_permission_from_session",
                        lambda _perm: actor())
    assert client.post(target, json={"product_ids": ["first"]}).status_code == 403
    assert len(fake.connection.statements) == 0

    monkeypatch.setattr(routes, "require_platform_permission_from_session",
                        lambda _perm: actor(True, False, "regular"))
    assert client.post(target, json={"product_ids": ["first"]}).status_code == 403

    monkeypatch.setattr(routes, "require_platform_permission_from_session",
                        lambda _perm: actor(False, True, "regular"))
    response = client.post(target, json={"product_ids": ["second", "first"]})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["second", "first"]
    assert client.post(target, json={"product_ids": ["first", "first"]}).status_code == 409
    assert client.post(target, json={"product_ids": ["deleted"]}).status_code == 409
    assert client.post(target, json={"product_ids": ["first"] * 101}).status_code == 422
    assert client.post(target, json={"product_ids": ["first"], "actor_id": "forged"}).status_code == 422
    assert client.get(target).status_code == 405

    monkeypatch.setattr(routes, "require_platform_permission_from_session",
                        lambda _perm: actor(True, False, "system"))
    assert client.post(target, json={"product_ids": ["first"]}).status_code == 200
