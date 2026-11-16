"""In-memory *fake* unit authority: no local SQL database or runtime override.

The production writers run on PostgreSQL. This fake supports only the SQL
statements used by the explicitly confirmed Catalogus scan flow; all other
queries and all receipt/household/inventory writes fail immediately.
"""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import barcode_routes
from app.services import barcode_identity_service
from app.services.barcode_identity_service import calculate_gtin_check_digit, lookup_gtin
from app.services.universal_scan_identification_service import (
    UniversalScanIdentityError, confirm_scanned_catalog_gtin,
)


def gtin(body):
    return body + str(calculate_gtin_check_digit(body))


class Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def scalar_one(self):
        assert len(self.rows) == 1
        return next(iter(self.rows[0].values()))


class CatalogOnlyConnection:
    def __init__(self):
        self.dialect = SimpleNamespace(name="isolated-contract")
        self.products = {}
        self.identities = []
        self.inventory_events = [{"id": "stock-before"}]
        self.household_articles = [{"id": "household-before"}]
        self.receipt_lines = [{"id": "receipt-before"}]
        self.sql_log = []

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        params = dict(params or {})
        self.sql_log.append(sql)
        if sql.startswith("SELECT id FROM global_products WHERE primary_gtin IN"):
            return Rows({"id": p["id"]} for p in self.products.values()
                        if p["primary_gtin"] in params["aliases"])
        if sql.startswith("SELECT global_product_id AS id FROM product_identities"):
            return Rows({"id": i["global_product_id"]} for i in self.identities
                        if i["identity_value"] in params["aliases"]
                        and i["identity_type"] in ("gtin", "ean", "upc"))
        if "FROM global_products gp" in sql and "ORDER BY CASE" in sql:
            code = params["gtin"]
            found = []
            for product in self.products.values():
                ident = next((i for i in self.identities
                              if i["global_product_id"] == product["id"]
                              and i["identity_type"] == "gtin"
                              and i["identity_value"] == code), None)
                if product["primary_gtin"] != code and ident is None:
                    continue
                found.append({
                    **product, "identity_id": ident["id"] if ident else None,
                    "identity_source": ident["source"] if ident else None,
                    "identity_is_primary": bool(ident["is_primary"]) if ident else False,
                    "has_matching_gtin_identity": 1 if ident else 0,
                    "product_type_key": None, "gpc_brick_code": None,
                    "product_type_name": None, "has_active_official_gpc": 0,
                })
            return Rows(found)
        if sql.startswith("INSERT INTO global_products"):
            assert params["id"] not in self.products
            assert all(p["primary_gtin"] != params["gtin"] for p in self.products.values())
            self.products[params["id"]] = {
                "id": params["id"], "primary_gtin": params["gtin"],
                "name": params["name"], "brand": None, "image_url": None,
                "status": "active",
            }
            return Rows()
        if sql.startswith("INSERT INTO product_identities"):
            self.identities.append({
                "id": params["id"], "global_product_id": params["product_id"],
                "identity_type": "gtin", "identity_value": params["gtin"],
                "source": "manual_scan_identification", "is_primary": True,
            })
            return Rows()
        raise AssertionError("Onverwachte databaseactie: " + sql)


class CatalogOnlyEngine:
    def __init__(self):
        self.conn = CatalogOnlyConnection()

    @contextmanager
    def begin(self):
        yield self.conn


@pytest.fixture
def database(monkeypatch):
    engine = CatalogOnlyEngine()
    monkeypatch.setattr(barcode_identity_service, "_table_names",
                        lambda _conn: {"global_products", "product_identities"})
    monkeypatch.setattr(barcode_identity_service, "_column_names",
                        lambda _conn, _table: {"image_url"})
    return engine


def test_register_explicit_gtin_without_receipt_household_or_stock(database):
    value = gtin("871234567890")
    conn = database.conn
    before = (list(conn.receipt_lines), list(conn.household_articles), list(conn.inventory_events))
    result = confirm_scanned_catalog_gtin(conn, barcode=value, product_name=" Melk  1 liter ")
    assert result["status"] == "created"
    assert result["stock_changes"] == result["receipt_changes"] == result["household_changes"] == 0
    assert result["product"]["name"] == "Melk 1 liter"
    lookup = lookup_gtin(conn, value)
    assert lookup["match_status"] == "matched"
    assert lookup["product"]["global_product_id"] == result["product"]["global_product_id"]
    assert len(conn.products) == len(conn.identities) == 1
    assert before == (conn.receipt_lines, conn.household_articles, conn.inventory_events)


def test_repeat_is_idempotent_and_does_not_rename(database):
    conn = database.conn
    value = gtin("871234567890")
    first = confirm_scanned_catalog_gtin(conn, barcode=value, product_name="Melk")
    again = confirm_scanned_catalog_gtin(conn, barcode=value, product_name="Andere naam")
    assert again["saved"] is False and again["status"] == "already_known"
    assert again["product"]["global_product_id"] == first["product"]["global_product_id"]
    assert next(iter(conn.products.values()))["name"] == "Melk"
    assert len(conn.identities) == 1


@pytest.mark.parametrize("code,name", [
    ("123", "Melk"),
    (gtin("201234567890"), "Winkelcode"),
    (gtin("871234567890"), ""),
    (gtin("871234567890"), "x" * 201),
])
def test_invalid_restricted_and_missing_name_fail_closed(database, code, name):
    with pytest.raises(UniversalScanIdentityError):
        confirm_scanned_catalog_gtin(database.conn, barcode=code, product_name=name)
    assert database.conn.products == {}


def test_incomplete_existing_product_requires_manual_review(database):
    conn = database.conn
    value = gtin("871234567890")
    conn.products["legacy"] = {
        "id": "legacy", "primary_gtin": value, "name": "Oude naam",
        "brand": None, "image_url": None, "status": "active",
    }
    with pytest.raises(UniversalScanIdentityError) as exc:
        confirm_scanned_catalog_gtin(conn, barcode=value, product_name="Nieuwe naam")
    assert exc.value.status_code == 409
    assert conn.products["legacy"]["name"] == "Oude naam"
    assert conn.identities == []


def test_equivalent_gtin_thirteen_fourteen_cannot_create_second_catalog_owner(database):
    conn = database.conn
    thirteen = gtin("871234567890")
    first = confirm_scanned_catalog_gtin(conn, barcode=thirteen, product_name="Melk")
    with pytest.raises(UniversalScanIdentityError) as exc:
        confirm_scanned_catalog_gtin(conn, barcode="0" + thirteen, product_name="Nieuwe melk")
    assert exc.value.status_code == 409
    assert len(conn.products) == len(conn.identities) == 1
    assert next(iter(conn.products)) == first["product"]["global_product_id"]


def test_route_denies_unprivileged_user_before_any_database_write(database, monkeypatch):
    monkeypatch.setattr(barcode_routes, "_require_auth", lambda _authorization: {"user_id": "other"})
    def deny(_permission):
        raise HTTPException(status_code=403, detail="Ontbrekende platformpermissie")
    monkeypatch.setattr(barcode_routes, "require_platform_permission_from_session", deny)
    def forbidden_writer(*_args, **_kwargs):
        raise AssertionError("Onbevoegde gebruiker bereikte de Catalogusschrijver")
    monkeypatch.setattr(barcode_routes, "confirm_scanned_catalog_gtin", forbidden_writer)
    monkeypatch.setattr(barcode_routes, "engine", database)
    with pytest.raises(HTTPException) as exc:
        barcode_routes.identify_scanned_catalog_barcode(
            {"gtin": gtin("871234567890"), "product_name": "Melk"}, authorization=None
        )
    assert exc.value.status_code == 403
    assert database.conn.products == {}


def test_authorized_route_requires_canonical_platform_permission(database, monkeypatch):
    permissions = []
    monkeypatch.setattr(barcode_routes, "_require_auth", lambda _authorization: {"user_id": "frontteam"})
    monkeypatch.setattr(barcode_routes, "require_platform_permission_from_session",
                        lambda permission: permissions.append(permission))
    monkeypatch.setattr(barcode_routes, "engine", database)
    result = barcode_routes.identify_scanned_catalog_barcode(
        {"gtin": gtin("871234567890"), "product_name": "Havermelk"}, authorization=None
    )
    assert result["saved"] is True
    assert permissions == ["platform.external_products.link_existing"]
    assert len(database.conn.inventory_events) == 1
    assert len(database.conn.household_articles) == 1


def test_off_suggestion_is_read_only_and_requires_permission(database, monkeypatch):
    value = gtin("871234567890")
    permissions = []
    calls = []
    monkeypatch.setattr(barcode_routes, "_require_auth", lambda _authorization: {"user_id": "frontteam"})
    monkeypatch.setattr(barcode_routes, "require_platform_permission_from_session",
                        lambda permission: permissions.append(permission))
    monkeypatch.setattr(barcode_routes, "lookup_off_product_by_gtin",
                        lambda gtin_value: calls.append(gtin_value) or {
                            "status": "found",
                            "product": {"gtin": value, "product_name": "OFF-havermelk"},
                            "mutated": False,
                        })
    before = (dict(database.conn.products), list(database.conn.identities),
              list(database.conn.inventory_events))
    result = barcode_routes.scanned_barcode_off_suggestion(value, authorization=None)
    assert result["status"] == "found" and result["mutated"] is False
    assert result["product"]["product_name"] == "OFF-havermelk"
    assert calls == [value]
    assert permissions == ["platform.external_products.link_existing"]
    assert before == (database.conn.products, database.conn.identities,
                      database.conn.inventory_events)


def test_off_suggestion_does_not_lookup_restricted_barcode(monkeypatch):
    monkeypatch.setattr(barcode_routes, "_require_auth", lambda _authorization: {"user_id": "frontteam"})
    monkeypatch.setattr(barcode_routes, "require_platform_permission_from_session", lambda _key: None)
    def forbid_external_request(_code):
        raise AssertionError("Winkelinterne code werd onveilig extern opgezocht")
    monkeypatch.setattr(barcode_routes, "lookup_off_product_by_gtin", forbid_external_request)
    with pytest.raises(HTTPException) as exc:
        barcode_routes.scanned_barcode_off_suggestion(gtin("201234567890"), authorization=None)
    assert exc.value.status_code == 409
