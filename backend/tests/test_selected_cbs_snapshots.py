"""Read-only bounded CBS snapshots for the migrated Artikelbeheer bulk actions."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool
from types import SimpleNamespace

from app.api import cbs_classification_routes as routes
from app.services.classification_server_paging_service import load_selected_cbs_snapshots


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE global_products (id TEXT PRIMARY KEY, name TEXT, status TEXT)"))
        conn.execute(text("CREATE TABLE global_product_cbs_classifications (global_product_id TEXT PRIMARY KEY, version INTEGER, is_active BOOLEAN)"))
        conn.execute(text("""INSERT INTO global_products VALUES
            ('first', 'Halfvolle melk', 'active'), ('second', 'Volle melk', 'active'),
            ('inactive', 'Eerder geclassificeerd', 'active'), ('deleted', 'Verwijderd', 'deleted')"""))
        conn.execute(text("""INSERT INTO global_product_cbs_classifications VALUES
            ('second', 3, TRUE), ('inactive', 7, FALSE), ('deleted', 2, TRUE)"""))
    yield engine
    engine.dispose()


def test_selects_exact_ids_in_request_order_and_preserves_versions_without_writes(db):
    queries = []
    def record(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement.strip().upper())
    event.listen(db, "before_cursor_execute", record)
    try:
        with db.connect() as conn:
            result = load_selected_cbs_snapshots(conn, ["inactive", "first", "second"])
    finally:
        event.remove(db, "before_cursor_execute", record)
    assert result == {"total": 3, "items": [
        {"id": "inactive", "name": "Eerder geclassificeerd", "version": 7, "classified": False},
        {"id": "first", "name": "Halfvolle melk", "version": 0, "classified": False},
        {"id": "second", "name": "Volle melk", "version": 3, "classified": True},
    ]}
    assert len(queries) == 1 and queries[0].startswith("SELECT")


@pytest.mark.parametrize("ids", [
    [], ["first", "first"], ["deleted"], ["missing"], ["first"] * 101, [""], ["x" * 201],
])
def test_rejects_incomplete_duplicate_deleted_and_oversized_selections(db, ids):
    with db.connect() as conn, pytest.raises(ValueError):
        load_selected_cbs_snapshots(conn, ids)


def test_api_enforces_platform_role_and_bounded_read_only_payload(monkeypatch, db):
    monkeypatch.setattr(routes, "engine", db)
    application = FastAPI()
    application.include_router(routes.router)
    client = TestClient(application)

    def actor(superuser=False, frontteam=False, context="regular"):
        return SimpleNamespace(is_platform_superuser=superuser, is_frontteam=frontteam,
                               context_type=context, user_id="member")
    monkeypatch.setattr(routes, "require_platform_permission_from_session",
                        lambda _perm: actor())
    target = "/api/cbs-classifications/workqueue-selected-cbs-snapshots"
    assert client.post(target, json={"product_ids": ["first"]}).status_code == 403

    monkeypatch.setattr(routes, "require_platform_permission_from_session",
                        lambda _perm: actor(True, False, "regular"))
    assert client.post(target, json={"product_ids": ["first"]}).status_code == 403

    monkeypatch.setattr(routes, "require_platform_permission_from_session",
                        lambda _perm: actor(False, True, "regular"))
    correct = client.post(target, json={"product_ids": ["second", "first"]})
    assert correct.status_code == 200
    assert [item["id"] for item in correct.json()["items"]] == ["second", "first"]
    assert client.post(target, json={"product_ids": ["first", "first"]}).status_code == 409
    assert client.post(target, json={"product_ids": ["deleted"]}).status_code == 409
    assert client.post(target, json={"product_ids": ["first"] * 101}).status_code == 422
    assert client.post(target, json={"product_ids": ["first"], "actor_id": "forged"}).status_code == 422
    assert client.get(target).status_code == 405

    monkeypatch.setattr(routes, "require_platform_permission_from_session",
                        lambda _perm: actor(True, False, "system"))
    assert client.post(target, json={"product_ids": ["first"]}).status_code == 200
