"""Exact household source evidence and fail-closed historical Catalogus review."""
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.api import catalog_household_identity_review_routes as routes


GTIN = "8712345678906"


class Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)
    def mappings(self):
        return self
    def all(self):
        return self.rows
    def first(self):
        return self.rows[0] if self.rows else None


class FakeConn:
    dialect = SimpleNamespace(name="postgresql")
    def __init__(self, *, missing=False, changed=False, existing_product=None,
                 existing_receipt_barcode="", legacy=False):
        self.missing = missing
        self.changed = changed
        self.existing_product = existing_product
        self.existing_receipt_barcode = existing_receipt_barcode
        self.legacy = legacy
        self.queries = []
    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.queries.append((sql, params))
        if "FROM purchase_import_lines pil" in sql:
            if self.missing:
                return Rows()
            return Rows([{
                "receipt_line_id": "receipt-1",
                "current_product_id": self.existing_product,
                "code": "0012345",
                "receipt_gtin": self.existing_receipt_barcode,
                "receipt_text": "Melk halfvol" if not self.changed else "Yoghurt",
                "retailer": "Lidl",
            }])
        if "FROM external_article_product_links" in sql:
            return Rows([("legacy",)] if self.legacy else [])
        raise AssertionError("Unexpected SQL: " + sql)


class FakeEngine:
    def __init__(self, conn):
        self.conn = conn
    @contextmanager
    def begin(self):
        yield self.conn
    @contextmanager
    def connect(self):
        yield self.conn


@pytest.fixture(autouse=True)
def authorized(monkeypatch):
    monkeypatch.setattr(
        routes, "require_platform_permission_from_session",
        lambda permission: SimpleNamespace(user_id="actor-1"),
    )
    monkeypatch.setattr(
        routes, "require_household_admin_from_session",
        lambda: {"user_id": "actor-1", "active_household_id": "1", "role": "owner"},
    )


def request(**overrides):
    params = dict(
        household_article_id="article-1", receipt_line_id="receipt-1",
        retailer_code="lidl", receipt_text="Melk halfvol",
        external_article_code="0012345", target_gtin=GTIN,
    )
    params.update(overrides)
    return routes.ConfirmConflictSourceRequest(**params)


def test_list_is_read_only_and_household_scoped(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(routes, "engine", FakeEngine(conn))
    seen = []
    def preview(_conn, **kwargs):
        seen.append(kwargs)
        return {
            "conflict": 2, "source_rows_examined": 6, "articles_examined": 4,
            "conflict_list_complete": True, "conflict_items": [{"household_article_id":"a"}],
            "conflict_products": [], "changes": "none",
        }
    monkeypatch.setattr(routes, "preview_household_catalog_identity_backfill", preview)
    result = routes.list_household_catalog_identity_conflicts()
    assert seen == [{"household_id": "1", "include_conflicts": True}]
    assert result["conflict_count"] == 2
    assert result["data_changed"] is False
    assert conn.queries == []


def test_no_platform_permission_means_no_read_or_write(monkeypatch):
    def denied(_permission):
        raise HTTPException(403, "Geen toegang")
    monkeypatch.setattr(routes, "require_platform_permission_from_session", denied)
    with pytest.raises(HTTPException) as error:
        routes.list_household_catalog_identity_conflicts()
    assert error.value.status_code == 403
    with pytest.raises(HTTPException):
        routes.confirm_household_catalog_source(request())


def test_no_active_household_or_wrong_actor_is_denied(monkeypatch):
    monkeypatch.setattr(routes, "require_household_admin_from_session",
                        lambda: {"user_id": "actor-1", "active_household_id": "0"})
    with pytest.raises(HTTPException) as error:
        routes.list_household_catalog_identity_conflicts()
    assert error.value.status_code == 403
    monkeypatch.setattr(routes, "require_household_admin_from_session",
                        lambda: {"user_id": "another", "active_household_id": "1"})
    with pytest.raises(HTTPException) as error:
        routes.list_household_catalog_identity_conflicts()
    assert error.value.status_code == 403


@pytest.mark.parametrize("conn_kwargs,request_kwargs", [
    ({"missing": True}, {}),
    ({"changed": True}, {}),
    ({"existing_product": "other-product"}, {}),
    ({"existing_receipt_barcode": "4006381333931"}, {}),
    ({"legacy": True}, {}),
])
def test_invalid_or_conflicting_source_blocks_confirmation(monkeypatch, conn_kwargs, request_kwargs):
    conn = FakeConn(**conn_kwargs)
    monkeypatch.setattr(routes, "engine", FakeEngine(conn))
    monkeypatch.setattr(routes, "resolve_catalog_identity",
                        lambda _conn, **kwargs: {"status": "matched", "global_product_id": "product-1"})
    called = []
    monkeypatch.setattr(routes, "confirm_scanned_retailer_identity",
                        lambda *args, **kwargs: called.append(kwargs))
    with pytest.raises(HTTPException) as error:
        routes.confirm_household_catalog_source(request(**request_kwargs))
    assert error.value.status_code == 409
    assert not called
    if conn.queries:
        assert conn.queries[0][1]["household"] == "1"


def test_invalid_gtin_is_rejected_before_database(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(routes, "engine", FakeEngine(conn))
    with pytest.raises(HTTPException) as error:
        routes.confirm_household_catalog_source(request(target_gtin="8712345678901"))
    assert error.value.status_code == 422
    assert conn.queries == []


def test_success_only_confirms_complete_source_key(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(routes, "engine", FakeEngine(conn))
    monkeypatch.setattr(routes, "resolve_catalog_identity",
                        lambda _conn, **kwargs: {"status": "matched", "global_product_id": "product-1"})
    calls = []
    def confirm(_conn, **kwargs):
        calls.append(kwargs)
        return {"status": "confirmed", "changes": 1, "global_product_id": "product-1"}
    monkeypatch.setattr(routes, "confirm_scanned_retailer_identity", confirm)
    result = routes.confirm_household_catalog_source(request())
    assert result["changed"] is True
    assert (result["household_article_changes"], result["stock_changes"], result["receipt_changes"]) == (0, 0, 0)
    assert calls == [{
        "retailer_code": "lidl", "receipt_text": "melk halfvol",
        "external_article_code": "0012345", "scanned_gtin": GTIN, "confirmed_by": "actor-1",
    }]
    assert conn.queries[0][1] == {
        "household": "1", "article": "article-1", "receipt_line": "receipt-1",
    }
    assert all(not sql.startswith(("UPDATE ", "DELETE ", "INSERT ")) for sql, _ in conn.queries)
