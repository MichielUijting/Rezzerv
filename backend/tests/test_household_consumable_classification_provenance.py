"""Automatic consumable classification must preserve unknown versus manual no."""
from __future__ import annotations

import pytest

from app import main as legacy


class _Conn:
    def __init__(self):
        self.writes = []

    def execute(self, query, params=None):
        self.writes.append((str(query), dict(params or {})))
        return self

    def mappings(self):
        return self

    def first(self):
        return {"naam": "Onbekend huishoudartikel", "consumable": None}


@pytest.mark.parametrize(("name", "explicit", "expected"), [
    ("Onbekend huishoudartikel", None, None),
    ("Verse halfvolle melk", None, 1),
    ("Verse halfvolle melk", False, 0),
    ("Onbekend huishoudartikel", False, 0),
    ("Onbekend huishoudartikel", True, 1),
])
def test_new_household_article_retains_classification_provenance(
    monkeypatch, name, explicit, expected,
):
    monkeypatch.setattr(legacy, "find_existing_household_article_name",
                        lambda conn, household_id, article_name: None)
    monkeypatch.setattr(legacy, "ensure_household_article_global_product_link",
                        lambda conn, article_id: None)
    conn = _Conn()
    article_id = legacy.ensure_household_article(
        conn, "house-1", name, consumable=explicit,
    )
    assert article_id
    inserts = [(sql, args) for sql, args in conn.writes
               if "INSERT INTO household_articles" in sql]
    assert len(inserts) == 1
    assert inserts[0][1]["consumable"] is expected
    assert inserts[0][1]["household_id"] == "house-1"


def test_unknown_existing_classification_is_not_persisted_as_manual_false(monkeypatch):
    monkeypatch.setattr(legacy, "infer_consumable_from_name", lambda name: False)
    conn = _Conn()
    assert legacy.get_article_consumable_state(
        conn, "house-1", "ha-1", "Onbekend huishoudartikel",
    ) is False
    assert len(conn.writes) == 1
    assert conn.writes[0][0].lstrip().startswith("SELECT")


def test_new_positive_evidence_fills_only_null_not_an_existing_user_decision(monkeypatch):
    monkeypatch.setattr(legacy, "infer_consumable_from_name", lambda name: True)
    conn = _Conn()
    assert legacy.get_article_consumable_state(
        conn, "house-1", "ha-1", "Verse halfvolle melk",
    ) is True
    assert len(conn.writes) == 2
    sql, params = conn.writes[-1]
    assert "consumable IS NULL" in sql
    assert "SET consumable = 1" in sql
    assert params["household_id"] == "house-1"


class _Scalars:
    def all(self):
        return []


class _InventoryConn:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((str(query), dict(params or {})))
        return self

    def scalars(self):
        return _Scalars()


@pytest.mark.parametrize(("name", "expected"), [
    ("Verse halfvolle melk", 1),
    ("Onbekend huishoudartikel", None),
])
def test_inventory_created_article_never_persists_unknown_as_nonconsumable(name, expected):
    conn = _InventoryConn()
    article_id = legacy.resolve_or_create_inventory_household_article(
        conn, household_id="house-1", article_name=name,
    )
    assert article_id
    inserts = [(sql, params) for sql, params in conn.calls
               if "INSERT INTO household_articles" in sql]
    assert len(inserts) == 1
    assert inserts[0][1]["consumable"] is expected
    assert inserts[0][1]["household_id"] == "house-1"
