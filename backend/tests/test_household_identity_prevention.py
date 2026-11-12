"""Regression gates: never recreate a deleted household identity from a receipt name.

The legacy FastAPI module also owns application startup. Extract only the real
production functions under test from its AST to exercise their branch decisions
without booting Docker, invoking a scheduler or touching user data.
"""
from __future__ import annotations

import ast
import copy
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"


def production_function(name: str, **dependencies):
    source = ast.parse(MAIN.read_text(encoding="utf-8"))
    matches = [node for node in source.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == name]
    assert len(matches) == 1, name
    node = copy.deepcopy(matches[0])
    node.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")],
                             level=0), node],
        type_ignores=[],
    ))
    env = {
        "HTTPException": HTTPException,
        "text": lambda statement: statement,
        "uuid": uuid,
        **dependencies,
    }
    exec(compile(module, str(MAIN), "exec"), env)
    return env[name]


def _same_name(value):
    return " ".join(str(value or "").strip().split())


class Scalar:
    def __init__(self, value=None):
        self.value = value

    def scalar(self):
        return self.value


class Mapping:
    def __init__(self, value=None):
        self.value = value

    def mappings(self):
        return self

    def first(self):
        return self.value


class FakeConn:
    def __init__(self, handler, dialect="sqlite"):
        self.handler = handler
        self.dialect = SimpleNamespace(name=dialect)
        self.statements = []

    def execute(self, statement, values=None):
        self.statements.append((str(statement), dict(values or {})))
        return self.handler(str(statement), values or {})


def test_receipt_description_cannot_prove_catalogus_identity():
    lookups = []
    def get_identity(_conn, _value, identity_types=None):
        lookups.append(tuple(identity_types or ()))
        return None
    fn = production_function(
        "find_global_product_match_for_receipt_line",
        normalize_barcode_value=_same_name,
        normalize_identity_lookup_value=_same_name,
        build_retailer_article_identity_value=lambda retailer, article: None,
        get_global_product_row_by_identity=get_identity,
    )
    # Even if a Catalogus product shares this exact name, name alone is not a key.
    assert fn(object(), None, "Rode bieten gekookt", None) is None
    assert fn(object(), None, "Broccoli", "Mijn merk",
              external_article_code="0082904") is None
    assert all("store_sku" not in types for types in lookups)


def test_receipt_store_code_is_never_masqueraded_as_gtin_during_sync():
    identity_calls = []
    def execute(sql, values):
        if "FROM purchase_import_lines" in sql:
            return Mapping({
                "id": "line1", "article_name_raw": "Aardappel iets kruimig",
                "brand_raw": None, "external_article_code": "0083242",
                "matched_household_article_id": None,
                "matched_global_product_id": None,
            })
        return Mapping()
    conn = FakeConn(execute)
    def resolve(_conn, *_args, **kwargs):
        identity_calls.append(kwargs)
        return {"matched_global_product_id": None, "matched_household_article_id": None}
    fn = production_function(
        "sync_purchase_import_line_product_links",
        resolve_receipt_line_product_links=resolve,
    )
    result = fn(conn, "line1", "household-1")
    assert result["matched_global_product_id"] is None
    assert len(identity_calls) == 1
    assert identity_calls[0]["barcode"] is None
    assert identity_calls[0]["external_article_code"] == "0083242"


def test_deleted_household_id_cannot_be_recreated_from_inventory_name():
    def execute(sql, _values):
        if "SELECT id FROM household_articles" in sql:
            return Scalar(None)
        raise AssertionError("After missing canonical ID no fallback SQL is permitted")
    conn = FakeConn(execute)
    fn = production_function(
        "resolve_or_create_inventory_household_article",
        normalize_household_article_name=_same_name,
    )
    with pytest.raises(HTTPException) as error:
        fn(conn, household_id="household-1", article_name="Broccoli",
           preferred_household_article_id="deleted-article-id")
    assert error.value.status_code == 409
    assert len(conn.statements) == 1
    assert not any("INSERT" in sql for sql, _ in conn.statements)


def test_deleted_id_with_stale_name_cannot_be_reconstructed_by_article_reference():
    created = []
    fn = production_function(
        "resolve_household_article_reference",
        normalize_household_article_name=_same_name,
        get_household_article_row_by_id=lambda *_: None,
        get_inventory_article_name_by_id=lambda *_: None,
        ensure_household_article=lambda *_: created.append(True),
    )
    with pytest.raises(HTTPException) as error:
        fn(object(), "household-1", article_id="deleted-record",
           article_name="Aardappel iets kruimig", create_if_missing=True)
    assert error.value.status_code == 409
    assert created == []


def test_deleted_live_alias_cannot_be_recreated():
    created = []
    fn = production_function(
        "resolve_household_article_reference",
        normalize_household_article_name=_same_name,
        get_household_article_row_by_name=lambda *_: None,
        ensure_household_article=lambda *_: created.append(True),
    )
    with pytest.raises(HTTPException) as error:
        fn(object(), "household-1", article_id="live::Broccoli",
           create_if_missing=True)
    assert error.value.status_code == 409
    assert not created


def test_existing_household_article_with_different_product_is_not_reassigned_by_name():
    calls = []
    def execute(sql, _values):
        calls.append(sql)
        if "FROM global_products" in sql:
            return Mapping({
                "id": "catalog-1", "name": "Broccoli", "primary_gtin": "8712345678906",
                "brand": None, "category": None,
            })
        raise AssertionError("No other database command should run after a name collision")
    conn = FakeConn(execute)
    fn = production_function(
        "ensure_household_article_for_global_product",
        find_household_article_for_global_product=lambda *_: None,
        normalize_household_article_name=_same_name,
        normalize_barcode_value=_same_name,
        get_household_article_row_by_name=lambda *_: {
            "id": "article-old", "global_product_id": "catalog-OTHER",
            "barcode": None,
        },
    )
    with pytest.raises(HTTPException) as error:
        fn(conn, "household-1", "catalog-1")
    assert error.value.status_code == 409
    assert not any("UPDATE" in sql or "INSERT" in sql for sql in calls)


def test_existing_product_is_reused_before_another_household_article_is_created():
    calls = []
    def execute(sql, _values):
        calls.append(sql)
        return Mapping()
    conn = FakeConn(execute, dialect="postgresql")
    fn = production_function(
        "ensure_household_article_for_global_product",
        find_household_article_for_global_product=lambda *_: {"id": "canonical-id"},
    )
    assert fn(conn, "household-1", "catalog-1") == "canonical-id"
    assert len(calls) == 1
    assert "pg_advisory_xact_lock" in calls[0]


def test_canonical_product_barcode_mismatch_rejected_before_insert():
    def execute(sql, _values):
        if "FROM global_products" in sql:
            return Mapping({
                "id": "catalog-1", "name": "Broccoli",
                "primary_gtin": "8712345678906", "brand": None, "category": None,
            })
        raise AssertionError("Mismatch must stop before any mutation")
    conn = FakeConn(execute)
    fn = production_function(
        "ensure_household_article_for_global_product",
        find_household_article_for_global_product=lambda *_: None,
        normalize_household_article_name=_same_name,
        normalize_barcode_value=_same_name,
    )
    with pytest.raises(HTTPException) as error:
        fn(conn, "household-1", "catalog-1", barcode="8712345678901")
    assert error.value.status_code == 409
