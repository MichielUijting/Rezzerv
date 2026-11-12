"""Catalogus receipt identity review: exact PO key, rights and guarded writes."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import catalog_retailer_code_review_routes as routes


def test_receipt_description_and_article_number_are_both_required():
    assert routes._key("Lidl", "  Yoghurt    Naturel ", " 0082904 ") == (
        "lidl", "yoghurt naturel", "0082904"
    )
    assert routes._key("Lidl", "Yoghurt Naturel", "0082904") != routes._key(
        "Lidl", "Yoghurt Naturel", "6604598"
    )
    assert routes._key("Lidl", "Yoghurt Naturel", "0082904") != routes._key(
        "Lidl", "Kwark Naturel", "0082904"
    )
    with pytest.raises(HTTPException) as exc:
        routes._key("lidl", "", "0082904")
    assert exc.value.status_code == 422


def test_unknown_action_rejected_before_any_database_write(monkeypatch):
    denied = []
    monkeypatch.setattr(routes, "require_platform_permission_from_session",
                        lambda permission: (denied.append(permission), SimpleNamespace(user_id="actor-test"))[1])
    with pytest.raises(HTTPException) as exc:
        routes.review_catalog_retailer_code("p1", routes.ReviewRequest(
            link_id="l1", expected_product_id="p1", retailer_code="lidl",
            receipt_text="Kaas", external_article_code="0082904",
            action="delete"
        ))
    assert exc.value.status_code == 422
    assert denied == ["platform.external_products.link_existing"]


def test_unauthorized_review_does_not_access_database(monkeypatch):
    def reject(_permission):
        raise HTTPException(403, "Geen toegang")
    monkeypatch.setattr(routes, "require_platform_permission_from_session", reject)
    with pytest.raises(HTTPException) as exc:
        routes.review_catalog_retailer_code("p1", routes.ReviewRequest(
            link_id="l1", expected_product_id="p1", retailer_code="lidl",
            receipt_text="Kaas", external_article_code="0082904",
            action="confirm"
        ))
    assert exc.value.status_code == 403


class Rows:
    def __init__(self, entries=(), rowcount=0):
        self.entries=list(entries)
        self.rowcount=rowcount
    def mappings(self): return self
    def all(self): return self.entries
    def first(self): return self.entries[0] if self.entries else None
    def scalars(self): return self


class Conn:
    dialect=SimpleNamespace(name="postgresql")
    def __init__(self, conflict=False, household=False):
        self.writes=0
        self.conflict=conflict
        self.household=household
    def execute(self, stmt, params=None):
        sql=" ".join(str(stmt).split())
        if sql.startswith("SELECT pg_advisory_xact_lock"): return Rows([(1,)])
        if "FROM external_article_product_links WHERE id=:id FOR UPDATE" in sql:
            return Rows([{"id":"l1","global_product_id":"p1","status":"confirmed",
                          "retailer_code":"lidl","receipt_text_normalized":"kaas",
                          "external_article_code":"0082904"}])
        if "FROM external_article_product_links WHERE retailer_code=:retailer AND receipt_text_normalized=:description" in sql:
            items=[{"id":"l1","global_product_id":"p1"}]
            if self.conflict:
                items.append({"id":"l2","global_product_id":"p2"})
            return Rows(items)
        if "SELECT DISTINCT global_product_id FROM external_article_product_links" in sql:
            return Rows(["p1"])
        if "FROM global_products WHERE primary_gtin=:gtin" in sql:
            return Rows([{"id":"p2","name":"Kaas nieuw","primary_gtin":"8712345678901"}])
        if "SELECT id FROM external_article_product_links WHERE retailer_code=:retailer" in sql:
            return Rows(["l1"])
        if "SELECT id FROM household_articles" in sql:
            return Rows([("h1",)] if self.household else [])
        if sql.startswith("UPDATE"):
            self.writes+=1
            return Rows(rowcount=1)
        raise AssertionError("Unexpected query "+sql)


class Engine:
    def __init__(self, **kwargs): self.conn=Conn(**kwargs)
    @contextmanager
    def begin(self): yield self.conn


def request(action="confirm", gtin=None):
    return routes.ReviewRequest(
        link_id="l1",expected_product_id="p1",retailer_code="lidl",
        receipt_text="Kaas",external_article_code="0082904",
        action=action,target_gtin=gtin,
    )


@pytest.fixture(autouse=True)
def allow_review(monkeypatch):
    monkeypatch.setattr(routes,"require_platform_permission_from_session",
                        lambda _permission: SimpleNamespace(user_id="actor-test"))


def test_other_product_for_same_receipt_triple_is_rejected_without_write(monkeypatch):
    engine=Engine(conflict=True)
    monkeypatch.setattr(routes,"engine",engine)
    with pytest.raises(HTTPException) as exc:
        routes.review_catalog_retailer_code("p1",request())
    assert exc.value.status_code==409
    assert engine.conn.writes==0


def test_confirm_persists_only_review_evidence(monkeypatch):
    engine=Engine()
    monkeypatch.setattr(routes,"engine",engine)
    result=routes.review_catalog_retailer_code("p1",request())
    assert result["status"]=="confirmed"
    assert engine.conn.writes==1


def test_existing_household_identity_blocks_remapping(monkeypatch):
    engine=Engine(household=True)
    monkeypatch.setattr(routes,"engine",engine)
    with pytest.raises(HTTPException) as exc:
        routes.review_catalog_retailer_code("p1",request("correct","8712345678901"))
    assert exc.value.status_code==409
    assert engine.conn.writes==0


def test_exact_unoccupied_code_can_be_corrected(monkeypatch):
    engine=Engine()
    monkeypatch.setattr(routes,"engine",engine)
    result=routes.review_catalog_retailer_code("p1",request("correct","8712345678901"))
    assert result["status"]=="corrected"
    assert result["global_product_id"]=="p2"
    assert engine.conn.writes==1
