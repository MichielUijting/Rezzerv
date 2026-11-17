"""The mobile unpack scanner must not write a changed article barcode.

Isolated route contract: no database instance, SQLite or user data.
"""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import barcode_routes


class Result:
    def __init__(self, barcode):
        self.barcode = barcode

    def mappings(self):
        return self

    def first(self):
        return {"barcode": self.barcode}


class FakeConnection:
    def __init__(self, barcode):
        self.barcode = barcode
        self.locked = []

    def execute(self, sql, args):
        statement = " ".join(str(sql).split())
        assert "FOR UPDATE" in statement, statement
        assert "WHERE id = :article_id AND household_id = :household_id" in statement
        assert args == {"article_id": "article1", "household_id": "household1"}
        self.locked.append(statement)
        return Result(self.barcode)


class FakeEngine:
    def __init__(self, barcode):
        self.conn = FakeConnection(barcode)

    @contextmanager
    def begin(self):
        yield self.conn


@pytest.fixture
def setup_route(monkeypatch):
    recorded = []
    monkeypatch.setattr(barcode_routes, "_require_auth", lambda _authorization: {"role": "admin"})
    monkeypatch.setattr(
        barcode_routes, "household_context_from_runtime_context",
        lambda _runtime_context: SimpleNamespace(role="admin", active_household_id="household1"),
    )
    def store(_conn, **kwargs):
        recorded.append(kwargs)
        return {"ok": True, "gtin": kwargs["gtin"]}
    monkeypatch.setattr(barcode_routes, "save_gtin_catalog_and_household_link", store)
    return recorded


def scan_payload(old_barcode):
    return {
        "purchase_import_line_id": "line1",
        "household_article_id": "article1",
        "expected_old_gtin": old_barcode,
        "article_name": "Melk",
    }


def test_new_barcode_confirmed_only_when_old_was_empty(setup_route, monkeypatch):
    engine = FakeEngine(None)
    monkeypatch.setattr(barcode_routes, "engine", engine)
    response = barcode_routes.save_barcode_for_household_article(
        "8712345678901", scan_payload(""), authorization=None,
    )
    assert response["ok"] is True
    assert engine.conn.locked
    assert len(setup_route) == 1


def test_stale_scan_fails_closed_before_calling_catalog_writer(setup_route, monkeypatch):
    engine = FakeEngine("8712345678901")
    monkeypatch.setattr(barcode_routes, "engine", engine)
    with pytest.raises(HTTPException) as error:
        barcode_routes.save_barcode_for_household_article(
            "8712345678925", scan_payload("8712345678999"), authorization=None,
        )
    assert error.value.status_code == 409
    assert engine.conn.locked
    assert not setup_route


def test_explicit_old_barcode_allows_exact_match(setup_route, monkeypatch):
    engine = FakeEngine("8712345678901")
    monkeypatch.setattr(barcode_routes, "engine", engine)
    response = barcode_routes.save_barcode_for_household_article(
        "8712345678925", scan_payload("8712345678901"), authorization=None,
    )
    assert response["ok"]
    assert len(setup_route) == 1
    assert setup_route[0]["household_article_id"] == "article1"
    assert setup_route[0]["purchase_import_line_id"] == "line1"
