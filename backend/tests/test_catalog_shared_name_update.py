"""Catalogus name changes only touch the universal product, never household stock."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import catalog_routes
from app.services.global_product_service import build_global_product_fingerprint


class Rows:
    def __init__(self, entries=(), rowcount=0):
        self.entries = list(entries)
        self.rowcount = rowcount

    def mappings(self):
        return self

    def first(self):
        return self.entries[0] if self.entries else None


class CatalogConn:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.items = {
            "p1": {
                "id": "p1", "name": "Aardappelschijfje spek-ui",
                "brand": "Testmerk", "variant": None,
                "size_value": None, "size_unit": None,
                "primary_gtin": "8712345678901",
                "product_fingerprint": build_global_product_fingerprint("Aardappelschijfje spek-ui", "Testmerk"),
                "status": "active",
            },
            "p2": {
                "id": "p2", "name": "Ander artikel",
                "brand": "Testmerk", "variant": None,
                "size_value": None, "size_unit": None,
                "primary_gtin": None,
                "product_fingerprint": build_global_product_fingerprint("Ander artikel", "Testmerk"),
                "status": "active",
            },
        }
        self.households = [
            {"household_id": "h1", "global_product_id": "p1", "stock": 3},
            {"household_id": "h2", "global_product_id": "p1", "stock": 7},
        ]
        self.writes = []

    def execute(self, sql, params=None):
        statement = " ".join(str(sql).split())
        params = params or {}
        if statement.startswith("SELECT id, name, status, primary_gtin, brand, variant"):
            row = self.items.get(params["product_id"])
            return Rows([dict(row)] if row else [])
        if statement.startswith("SELECT id FROM global_products WHERE product_fingerprint"):
            return Rows([
                (row["id"],) for row in self.items.values()
                if row["id"] != params["product_id"]
                and row["product_fingerprint"] == params["fingerprint"]
                and row["status"] == "active"
                and not row["primary_gtin"]
            ][:1])
        if statement.startswith("UPDATE global_products SET name ="):
            row = self.items.get(params["product_id"])
            if not row or row["name"] != params["expected_name"]:
                return Rows(rowcount=0)
            row["name"] = params["new_name"]
            row["product_fingerprint"] = params["fingerprint"]
            self.writes.append(statement)
            return Rows(rowcount=1)
        raise AssertionError("Onverwachte SQL: " + statement)


class CatalogEngine:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def begin(self):
        yield self.conn


@pytest.fixture
def db(monkeypatch):
    conn = CatalogConn()
    auth_calls = []
    monkeypatch.setattr(catalog_routes, "engine", CatalogEngine(conn))
    monkeypatch.setattr(catalog_routes, "_columns", lambda table: {
        "id", "name", "status", "primary_gtin", "brand", "variant",
        "size_value", "size_unit", "product_fingerprint", "updated_at",
    })
    monkeypatch.setattr(
        catalog_routes, "require_platform_permission_from_session",
        lambda perm: auth_calls.append(perm),
    )
    return conn, auth_calls


def update(name, old="Aardappelschijfje spek-ui", product_id="p1"):
    return catalog_routes.update_catalog_product_name(
        product_id,
        catalog_routes.CatalogNameUpdateRequest(name=name, expected_name=old),
    )


def test_rename_changes_shared_name_and_fingerprint_only(db):
    conn, calls = db
    before = list(map(dict, conn.households))
    gtin = conn.items["p1"]["primary_gtin"]
    result = update("  Aardappelschijfjes   spek-ui  ")
    assert result == {"global_product_id": "p1", "name": "Aardappelschijfjes spek-ui", "changed": True}
    assert calls == ["platform.catalog.update"]
    assert conn.items["p1"]["name"] == "Aardappelschijfjes spek-ui"
    assert conn.items["p1"]["primary_gtin"] == gtin
    assert conn.items["p1"]["product_fingerprint"] == build_global_product_fingerprint(
        "Aardappelschijfjes spek-ui", "Testmerk"
    )
    assert conn.households == before
    assert len(conn.writes) == 1


def test_same_name_is_idempotent(db):
    conn, _ = db
    assert update("Aardappelschijfje spek-ui")["changed"] is False
    assert conn.writes == []


def test_missing_and_overlong_names_rejected(db):
    for value in (" ", "X" * 201):
        with pytest.raises(ValidationError):
            catalog_routes.CatalogNameUpdateRequest(
                name=value, expected_name="Aardappelschijfje spek-ui",
            )
    assert db[0].writes == []


def test_stale_name_blocks_overwriting_someone_else_edit(db):
    conn, _ = db
    conn.items["p1"]["name"] = "Intussen gewijzigd"
    with pytest.raises(HTTPException) as error:
        update("Nieuwe naam")
    assert error.value.status_code == 409
    assert conn.writes == []


def test_collision_with_existing_unbarcoded_product_refused(db):
    conn, _ = db
    with pytest.raises(HTTPException) as error:
        update("Ander artikel")
    assert error.value.status_code == 409
    assert conn.writes == []


def test_deleted_or_missing_product_rejected(db):
    conn, _ = db
    conn.items["p1"]["status"] = "deleted"
    with pytest.raises(HTTPException) as error:
        update("Nieuwe naam")
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        update("Nieuwe naam", product_id="absent")
    assert error.value.status_code == 404


def test_only_catalog_authorized_users_can_rename(db, monkeypatch):
    conn, _ = db

    def denied(_permission):
        raise HTTPException(status_code=403, detail="Geen catalogusbeheer")

    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session", denied)
    with pytest.raises(HTTPException) as error:
        update("Nieuwe naam")
    assert error.value.status_code == 403
    assert conn.writes == []


def test_name_change_does_not_require_or_use_household_admin_fallback(db, monkeypatch):
    conn, _ = db
    def unexpected():
        raise AssertionError("Huishoudbeheerder mag niet zonder meer centrale namen wijzigen")
    monkeypatch.setattr(catalog_routes, "require_household_admin_from_session", unexpected)
    assert update("Nieuwe naam")["changed"] is True
    assert len(conn.writes) == 1
