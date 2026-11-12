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
    actor = SimpleNamespace(
        user_id="actor-1", active_household_id="1",
        context_type="regular", is_frontteam=True, is_platform_superuser=False,
    )
    monkeypatch.setattr(routes, "resolve_current_server_session", lambda: actor)
    monkeypatch.setattr(routes, "require_platform_permission_from_session", lambda _permission: actor)
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


def test_system_superuser_still_requires_platform_permission(monkeypatch):
    monkeypatch.setattr(routes, "resolve_current_server_session",
                        lambda: SimpleNamespace(user_id="system", active_household_id="0",
                                                context_type="system", is_platform_superuser=True))
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


@pytest.mark.parametrize("session", [
    dict(user_id="actor-1", active_household_id="1",
         context_type="none", is_frontteam=False, is_platform_superuser=False),
    dict(user_id="actor-1", active_household_id="1",
         context_type="system", is_frontteam=False, is_platform_superuser=True),
    dict(user_id="actor-1", active_household_id="0",
         context_type="system", is_frontteam=False, is_platform_superuser=False),
    dict(user_id="actor-1", active_household_id="0",
         context_type="regular", is_frontteam=True, is_platform_superuser=False),
])
def test_other_roles_or_invalid_household_context_cannot_read_or_confirm(monkeypatch, session):
    conn = FakeConn()
    monkeypatch.setattr(routes, "engine", FakeEngine(conn))
    monkeypatch.setattr(routes, "resolve_current_server_session",
                        lambda: SimpleNamespace(**session))
    with pytest.raises(HTTPException) as list_error:
        routes.list_household_catalog_identity_conflicts()
    assert list_error.value.status_code == 403
    with pytest.raises(HTTPException) as write_error:
        routes.confirm_household_catalog_source(request())
    assert write_error.value.status_code == 403
    assert conn.queries == []


def test_superuser_may_review_only_its_system_household_without_household_admin(monkeypatch):
    conn = FakeConn(missing=True)
    monkeypatch.setattr(routes, "engine", FakeEngine(conn))
    system_actor = SimpleNamespace(
        user_id="superuser", active_household_id="0",
        context_type="system", is_frontteam=False, is_platform_superuser=True,
    )
    monkeypatch.setattr(routes, "resolve_current_server_session", lambda: system_actor)
    monkeypatch.setattr(routes, "require_platform_permission_from_session",
                        lambda _permission: system_actor)
    def household_admin_not_allowed():
        raise AssertionError("Superuser must not impersonate household admin")
    monkeypatch.setattr(routes, "require_household_admin_from_session",
                        household_admin_not_allowed)
    scoped = []
    def preview(_conn, **kwargs):
        scoped.append(kwargs)
        return {
            "conflict": 0, "source_rows_examined": 0, "articles_examined": 0,
            "conflict_list_complete": True, "conflict_items": [], "conflict_products": [],
        }
    monkeypatch.setattr(routes, "preview_household_catalog_identity_backfill", preview)
    result = routes.list_household_catalog_identity_conflicts()
    assert result["conflict_count"] == 0
    assert scoped == [{"household_id": "0", "include_conflicts": True}]

    with pytest.raises(HTTPException) as error:
        routes.confirm_household_catalog_source(request())
    assert error.value.status_code == 409
    assert conn.queries[0][1]["household"] == "0"
    assert conn.queries[0][1]["article"] == "article-1"
    assert conn.queries[0][1]["receipt_line"] == "receipt-1"


def test_frontteam_must_be_household_admin_and_match_session_household(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(routes, "engine", FakeEngine(conn))
    monkeypatch.setattr(routes, "require_household_admin_from_session",
                        lambda: (_ for _ in ()).throw(HTTPException(403, "Geen huishoudrechten")))
    with pytest.raises(HTTPException) as error:
        routes.list_household_catalog_identity_conflicts()
    assert error.value.status_code == 403
    assert conn.queries == []

    monkeypatch.setattr(routes, "require_household_admin_from_session",
                        lambda: {"user_id": "actor-1", "active_household_id": "different"})
    with pytest.raises(HTTPException) as error:
        routes.list_household_catalog_identity_conflicts()
    assert error.value.status_code == 403
    assert conn.queries == []


@pytest.mark.parametrize("role", ["owner", "admin"])
def test_regular_household_manager_can_read_without_platform_permissions(monkeypatch, role):
    conn = FakeConn()
    monkeypatch.setattr(routes, "engine", FakeEngine(conn))
    monkeypatch.setattr(routes, "resolve_current_server_session",
                        lambda: SimpleNamespace(
                            user_id="manager", active_household_id="household-one",
                            context_type="regular", is_frontteam=False,
                            is_platform_superuser=False))
    monkeypatch.setattr(routes, "require_household_admin_from_session",
                        lambda: {"user_id": "manager",
                                 "active_household_id": "household-one", "role": role})
    def reject_platform_permission(_permission):
        raise AssertionError("Household managers are not given platform Catalogus authority")
    monkeypatch.setattr(routes, "require_platform_permission_from_session", reject_platform_permission)
    scopes = []
    def read_only_preview(_conn, **kwargs):
        scopes.append(kwargs)
        return {
            "conflict": 1, "source_rows_examined": 8, "articles_examined": 2,
            "conflict_list_complete": True, "conflict_items": [], "conflict_products": [],
        }
    monkeypatch.setattr(routes, "preview_household_catalog_identity_backfill", read_only_preview)
    result = routes.list_household_catalog_identity_conflicts()
    assert result["conflict_count"] == 1
    assert scopes == [{"household_id": "household-one", "include_conflicts": True}]
    assert conn.queries == []


def test_manager_can_confirm_own_receipt_source_without_platform_role(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(routes, "engine", FakeEngine(conn))
    monkeypatch.setattr(routes, "resolve_current_server_session",
                        lambda: SimpleNamespace(user_id="manager", active_household_id="household-one",
                                                context_type="regular", is_frontteam=False))
    monkeypatch.setattr(routes, "require_household_admin_from_session",
                        lambda: {"user_id": "manager", "active_household_id": "household-one",
                                 "role": "admin"})
    monkeypatch.setattr(routes, "require_platform_permission_from_session",
                        lambda _: (_ for _ in ()).throw(AssertionError("no platform privilege")))
    monkeypatch.setattr(routes, "resolve_catalog_identity",
                        lambda _conn, **kwargs: {"status": "matched", "global_product_id": "product-1"})
    confirmations = []
    monkeypatch.setattr(routes, "confirm_scanned_retailer_identity",
                        lambda _conn, **kwargs: (
                            confirmations.append(kwargs) or
                            {"status": "confirmed", "changes": 1, "global_product_id": "product-1"}
                        ))
    result = routes.confirm_household_catalog_source(request())
    assert result["changed"] is True
    assert confirmations[0]["confirmed_by"] == "manager"
    assert conn.queries[0][1]["household"] == "household-one"
    assert result["stock_changes"] == 0 and result["household_article_changes"] == 0


@pytest.mark.parametrize("role", ["member", "viewer", "advanced_member", ""])
def test_regular_non_manager_is_denied_even_if_household_helper_is_misconfigured(monkeypatch, role):
    conn = FakeConn()
    monkeypatch.setattr(routes, "engine", FakeEngine(conn))
    monkeypatch.setattr(routes, "require_household_admin_from_session",
                        lambda: {"user_id": "actor-1", "active_household_id": "1", "role": role})
    with pytest.raises(HTTPException) as exc:
        routes.list_household_catalog_identity_conflicts()
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        routes.confirm_household_catalog_source(request())
    assert exc.value.status_code == 403
    assert conn.queries == []


def test_manager_with_other_household_context_cannot_read_or_write(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(routes, "engine", FakeEngine(conn))
    monkeypatch.setattr(routes, "resolve_current_server_session",
                        lambda: SimpleNamespace(user_id="manager", active_household_id="1",
                                                context_type="regular", is_frontteam=False))
    monkeypatch.setattr(routes, "require_household_admin_from_session",
                        lambda: {"user_id": "manager", "active_household_id": "2", "role": "owner"})
    with pytest.raises(HTTPException) as exc:
        routes.list_household_catalog_identity_conflicts()
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        routes.confirm_household_catalog_source(request())
    assert exc.value.status_code == 403
    assert conn.queries == []
