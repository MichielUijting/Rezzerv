"""Article-detail inventory preview is exact-id and household scoped.

Exercise the actual legacy route body with a tiny read-only SQL fake. Importing
app.main during pytest would start unrelated runtime integrations; the AST
extract retains the exact endpoint logic without booting the application.
"""
from __future__ import annotations

import ast
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import HTTPException


MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _ReadOnlyConnection:
    def __init__(self):
        self.calls = []
        self.inventory = [
            {"id": "inv-a", "household_article_id": "article-a", "household_id": "household-a",
             "artikel": "Rijst", "aantal": 2, "locatie": "Keuken", "sublocatie": "",
             "space_id": "space-1", "sublocation_id": None},
            {"id": "inv-b", "household_article_id": "article-b", "household_id": "household-a",
             "artikel": "Rijst", "aantal": 3, "locatie": "Berging", "sublocatie": "",
             "space_id": "space-2", "sublocation_id": None},
            {"id": "inv-foreign", "household_article_id": "article-a", "household_id": "household-b",
             "artikel": "Rijst", "aantal": 99, "locatie": "Andere woning", "sublocatie": "",
             "space_id": "space-3", "sublocation_id": None},
        ]

    def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, dict(params)))
        assert "FROM inventory i" in sql, "GET must not write to the database"
        assert "i.household_id = :household_id" in sql
        assert "COALESCE(i.status, 'active') = 'active'" in sql
        selected = [row for row in self.inventory
                    if row["household_id"] == params["household_id"]]
        if "household_article_id" in params:
            assert "i.household_article_id = :household_article_id" in sql
            selected = [row for row in selected
                        if row["household_article_id"] == params["household_article_id"]]
        else:
            assert "i.household_article_id = :household_article_id" not in sql
        return _Result(selected)


def _route(connection, seen):
    module = ast.parse(MAIN.read_text(encoding="utf-8"))
    endpoint = next(node for node in module.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "dev_inventory_preview")
    row_projection = next(node for node in module.body
                          if isinstance(node, ast.FunctionDef)
                          and node.name == "_dev_inventory_preview_row")
    endpoint.decorator_list = []
    code = compile(ast.fix_missing_locations(ast.Module(
        body=[row_projection, endpoint], type_ignores=[],
    )), str(MAIN), "exec")
    env = {
        "Optional": Optional,
        "Header": lambda default=None: default,
        "Query": lambda default=None: default,
        "HTTPException": HTTPException,
        "perf_counter": lambda: 0.0,
        "require_household_context": lambda _authorization: {
            "active_household_id": "household-a",
        },
        "household_context_from_runtime_context": lambda _context:
            SimpleNamespace(active_household_id="household-a"),
        "engine": SimpleNamespace(begin=lambda: nullcontext(connection)),
        "text": lambda query: query,
        "dutch_gpc_by_household_article": lambda _conn, hh, ids:
            seen.append((hh, list(ids))) or {},
    }
    exec(code, env)
    return env["dev_inventory_preview"]


def test_detail_request_returns_only_exact_article_without_similarly_named_peer():
    db, seen = _ReadOnlyConnection(), []
    response = _route(db, seen)(
        authorization="Bearer test-session", household_article_id="article-a")
    assert [row["id"] for row in response["rows"]] == ["inv-a"]
    assert [row["household_article_id"] for row in response["rows"]] == ["article-a"]
    assert len(db.calls) == 1
    assert db.calls[0][1] == {
        "household_id": "household-a", "household_article_id": "article-a"}
    assert seen == [("household-a", ["article-a"])]


def test_unknown_article_is_not_replaced_by_same_name_or_other_household():
    db, seen = _ReadOnlyConnection(), []
    response = _route(db, seen)(
        authorization="Bearer test-session", household_article_id="article-unknown")
    assert response["rows"] == []
    assert seen == [("household-a", [])]
    response = _route(db, seen)(
        authorization="Bearer test-session", household_article_id=" article-b ")
    assert [row["id"] for row in response["rows"]] == ["inv-b"]


def test_legacy_unfiltered_preview_remains_functionally_unchanged():
    db, seen = _ReadOnlyConnection(), []
    response = _route(db, seen)(
        authorization="Bearer test-session", household_article_id=None)
    assert [row["id"] for row in response["rows"]] == ["inv-a", "inv-b"]
    assert "household_article_id" not in db.calls[0][1]
    assert len(seen) == 1


def test_empty_supplied_article_id_is_rejected_without_database_read():
    db, seen = _ReadOnlyConnection(), []
    with pytest.raises(HTTPException) as exc:
        _route(db, seen)(authorization="Bearer test-session", household_article_id="  ")
    assert exc.value.status_code == 400
    assert db.calls == []
    assert seen == []
