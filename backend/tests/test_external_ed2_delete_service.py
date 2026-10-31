"""Targeted identity, permission, and non-destructive ED2 deletion contracts.

This is a pure transaction double: SQLite is not an alternative runtime or
integration authority. PostgreSQL schema and lifecycle gates remain mandatory.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import external_ed2_delete_service as service
from app.api import system_routes


class _Rows:
    def __init__(self, items=(), rowcount=0):
        self.items = list(items)
        self.rowcount = rowcount

    def mappings(self):
        return self

    def first(self):
        return self.items[0] if self.items else None

    def all(self):
        return self.items


class _Transaction:
    def __init__(self, state):
        self.state = state
        self.dialect = SimpleNamespace(name="postgresql")

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        params = params or {}
        product_id = params.get("id")
        if sql.startswith("SELECT id, status FROM global_products"):
            product = self.state["products"].get(product_id)
            return _Rows([{"id": product_id, "status": product}] if product else [])
        if sql.startswith("SELECT 1 FROM article_synonym_links"):
            return _Rows([{"present": 1}] if self.state["synonym"] else [])
        if "FROM external_article_product_links" in sql and sql.startswith("SELECT"):
            return _Rows([
                dict(link) for link in self.state["links"].values()
                if link["global_product_id"] == product_id
                and link["status"] in {"confirmed", "classification_pending"}
            ])
        if sql.startswith("INSERT INTO ed2_removed_articles"):
            self.state["hidden"].add((
                params["retailer"], params["label"], params["code"]
            ))
            return _Rows(rowcount=1)
        if sql.startswith("UPDATE external_article_product_links"):
            affected = 0
            for link in self.state["links"].values():
                if link["global_product_id"] == product_id and link["status"] in {
                    "confirmed", "classification_pending"
                }:
                    link["status"] = "inactive"
                    affected += 1
            return _Rows(rowcount=affected)
        if sql.startswith("UPDATE global_products"):
            if self.state["products"].get(product_id) != "active":
                return _Rows(rowcount=0)
            self.state["products"][product_id] = "deleted"
            return _Rows(rowcount=1)
        raise AssertionError(f"Unexpected SQL in ED2 deletion: {sql}")


class _Engine:
    def __init__(self, state):
        self.state = state

    @contextmanager
    def begin(self):
        working = deepcopy(self.state)
        yield _Transaction(working)
        self.state = working


def _make_database(monkeypatch, *, shared=False, with_product=True, synonym=False):
    engine = _Engine({
        "hidden": set(),
        "products": {"gp-1": "active"} if with_product else {},
        "links": {
            "ln-1": {
                "id": "ln-1", "retailer_code": "lidl",
                "receipt_text_normalized": "melk", "external_article_code": "123",
                "global_product_id": "gp-1", "status": "confirmed",
            }
        } if with_product else {},
        "synonym": synonym,
        "receipts": ["historische bon behouden"],
        "inventory": ["voorraad behouden"],
    })
    rows = [{
        "id": "receipt-table-line:r1", "retailer_code": "lidl",
        "receipt_line_text": "Melk", "receipt_article_number": "123",
        "catalog_product_id": "gp-1" if with_product else "",
    }]
    if shared:
        rows.append({
            "id": "receipt-table-line:r2", "retailer_code": "lidl",
            "receipt_line_text": "Andere melk", "receipt_article_number": "456",
            "catalog_product_id": "gp-1",
        })

    def overview(*, conn):
        hidden = conn.state["hidden"]
        visible = [row for row in rows if (
            row["retailer_code"], row["receipt_line_text"],
            row["receipt_article_number"]
        ) not in hidden]
        return {"items": visible, "total": len(visible)}

    monkeypatch.setattr(service, "engine", engine)
    monkeypatch.setattr(service, "list_all_external_articles", overview)
    monkeypatch.setattr(service, "inspect", lambda conn: SimpleNamespace(
        get_table_names=lambda: [
            "ed2_removed_articles", "global_products",
            "external_article_product_links",
            *(["article_synonym_links"] if synonym else []),
        ],
    ))
    return engine


def test_removal_is_atomic_and_preserves_receipts_and_inventory(monkeypatch):
    engine = _make_database(monkeypatch)
    result = service.remove_selected_ed2_articles([
        {"receipt_item_id": "receipt-table-line:r1"},
    ])
    assert result["ok"] is True
    assert result["removed_articles"] == 1
    assert result["removed_catalog_products"] == 1
    assert engine.state["products"]["gp-1"] == "deleted"
    assert engine.state["links"]["ln-1"]["status"] == "inactive"
    assert engine.state["hidden"] == {("lidl", "Melk", "123")}
    assert engine.state["receipts"] == ["historische bon behouden"]
    assert engine.state["inventory"] == ["voorraad behouden"]


def test_unlinked_article_only_disappears_from_ed2(monkeypatch):
    engine = _make_database(monkeypatch, with_product=False)
    result = service.remove_selected_ed2_articles([
        {"receipt_item_id": "receipt-table-line:r1"},
    ])
    assert result["removed_catalog_products"] == 0
    assert engine.state["hidden"] == {("lidl", "Melk", "123")}


def test_shared_catalog_identity_blocks_every_write(monkeypatch):
    engine = _make_database(monkeypatch, shared=True)
    with pytest.raises(ValueError, match="andere bonartikelen"):
        service.remove_selected_ed2_articles([
            {"receipt_item_id": "receipt-table-line:r1"},
        ])
    assert engine.state["hidden"] == set()
    assert engine.state["products"]["gp-1"] == "active"


def test_synonym_catalog_identity_blocks_every_write(monkeypatch):
    engine = _make_database(monkeypatch, synonym=True)
    with pytest.raises(ValueError, match="artikelsynoniemen"):
        service.remove_selected_ed2_articles([
            {"receipt_item_id": "receipt-table-line:r1"},
        ])
    assert engine.state["hidden"] == set()


@pytest.mark.parametrize("selection", [
    [], [{"receipt_item_id": ""}],
    [{"receipt_item_id": "r1"}, {"receipt_item_id": "r1"}],
    [{"receipt_item_id": "no-such-source"}],
])
def test_invalid_or_stale_selection_is_fail_closed(monkeypatch, selection):
    engine = _make_database(monkeypatch)
    with pytest.raises(ValueError):
        service.remove_selected_ed2_articles(selection)
    assert engine.state["hidden"] == set()
    assert engine.state["products"]["gp-1"] == "active"


def test_delete_route_requires_catalog_superuser_not_only_external_link_permission(monkeypatch):
    def deny():
        raise HTTPException(status_code=403, detail="Alleen de superuser")
    monkeypatch.setattr(system_routes, "_require_catalog_delete_superuser", deny)
    monkeypatch.setattr(system_routes, "remove_selected_ed2_articles",
                        lambda *_: pytest.fail("Deletion must not run without superuser"))
    with pytest.raises(HTTPException) as exc:
        system_routes.external_databases_delete_selected_articles({
            "selections": [{"receipt_item_id": "receipt-table-line:r1"}],
        })
    assert exc.value.status_code == 403
