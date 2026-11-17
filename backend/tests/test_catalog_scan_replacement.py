"""Fail-closed Catalogus GTIN replacement contract without SQLite or live data."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import catalog_routes
from app.services.barcode_identity_service import calculate_gtin_check_digit


def barcode(body):
    return body + str(calculate_gtin_check_digit(body))


class Result:
    def __init__(self, rows=(), rowcount=1):
        self.rows = list(rows)
        self.rowcount = rowcount

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class FakeCatalog:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.products = {
            "p1": {"id": "p1", "status": "active", "primary_gtin": barcode("871234567890")},
            "p2": {"id": "p2", "status": "active", "primary_gtin": None},
        }
        self.identities = []
        self.households = []
        self.retailers = []
        self.inventory = [{"id": "unchanged"}]

    def execute(self, command, args=None):
        sql = " ".join(str(command).split())
        args = dict(args or {})
        if sql.startswith("SELECT pg_advisory_xact_lock"):
            return Result([(1,)])
        if sql.startswith("SELECT id, status, primary_gtin FROM global_products"):
            item = self.products.get(args["product_id"])
            return Result([item] if item else [])
        if sql.startswith("SELECT id FROM global_products WHERE primary_gtin"):
            return Result(
                {"id": p["id"]} for p in self.products.values()
                if p["id"] != args["product_id"] and p["primary_gtin"] in args["aliases"]
            )
        if sql.startswith("SELECT global_product_id FROM product_identities"):
            return Result(
                {"global_product_id": i["global_product_id"]} for i in self.identities
                if i["identity_value"] in args["aliases"]
                and i["identity_type"] in ("gtin", "ean", "upc")
            )
        if sql.startswith("SELECT id FROM household_articles"):
            return Result({"id": h["id"]} for h in self.households
                          if h["global_product_id"] == args["product_id"])
        if sql.startswith("SELECT global_product_id FROM external_article_product_links"):
            return Result({"global_product_id": r["global_product_id"]} for r in self.retailers
                          if r["global_product_id"] == args["product_id"])
        if sql.startswith("UPDATE global_products SET primary_gtin"):
            product = self.products[args["product_id"]]
            if product["primary_gtin"] != args["old_gtin"]:
                return Result(rowcount=0)
            product["primary_gtin"] = args["new_gtin"]
            return Result(rowcount=1)
        raise AssertionError("Unexpected SQL: " + sql)


class Engine:
    def __init__(self):
        self.conn = FakeCatalog()

    @contextmanager
    def begin(self):
        yield self.conn


@pytest.fixture
def db(monkeypatch):
    engine = Engine()
    monkeypatch.setattr(catalog_routes, "engine", engine)
    monkeypatch.setattr(catalog_routes, "_tables",
                        lambda: {"global_products", "product_identities",
                                 "household_articles", "external_article_product_links"})
    monkeypatch.setattr(catalog_routes, "_columns",
                        lambda name: {
                            "global_products": {"id", "status", "primary_gtin", "updated_at"},
                            "product_identities": {"identity_type", "identity_value", "global_product_id"},
                            "household_articles": {"global_product_id"},
                            "external_article_product_links": {"global_product_id"},
                        }.get(name, set()))
    permitted = []
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session",
                        lambda key: permitted.append(key))
    return engine.conn, permitted


def change(old=None, new=None):
    return catalog_routes.replace_catalog_primary_gtin(
        "p1",
        catalog_routes.CatalogGtinReplaceRequest(
            gtin=new or barcode("871234567891"),
            expected_old_gtin=old or barcode("871234567890"),
        ),
    )


def test_confirmed_standalone_catalog_barcode_can_be_replaced(db):
    conn, permissions = db
    before = list(conn.inventory)
    result = change()
    assert result["changed"] is True
    assert conn.products["p1"]["primary_gtin"] == result["gtin"]
    assert permissions == ["platform.catalog.update"]
    assert conn.inventory == before


def test_stale_existing_barcode_is_rejected(db):
    conn, _ = db
    with pytest.raises(HTTPException) as err:
        change(old=barcode("871234567892"))
    assert err.value.status_code == 409
    assert conn.products["p1"]["primary_gtin"] == barcode("871234567890")


@pytest.mark.parametrize("use_link", ["identity", "household", "retailer"])
def test_existing_links_cannot_be_silently_rewritten(db, use_link):
    conn, _ = db
    if use_link == "identity":
        conn.identities.append({
            "identity_type": "gtin", "identity_value": barcode("871234567890"),
            "global_product_id": "p1",
        })
    elif use_link == "household":
        conn.households.append({"id": "h1", "global_product_id": "p1"})
    else:
        conn.retailers.append({"global_product_id": "p1"})
    with pytest.raises(HTTPException) as err:
        change()
    assert err.value.status_code == 409
    assert conn.products["p1"]["primary_gtin"] == barcode("871234567890")


def test_new_code_cannot_steal_existing_catalog_barcode(db):
    conn, _ = db
    conn.products["p2"]["primary_gtin"] = barcode("871234567891")
    with pytest.raises(HTTPException) as err:
        change()
    assert err.value.status_code == 409


def test_unauthorized_user_never_gets_write(db, monkeypatch):
    conn, _ = db
    def deny(_key):
        raise HTTPException(status_code=403, detail="Geen platformrechten")
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session", deny)
    with pytest.raises(HTTPException) as err:
        change()
    assert err.value.status_code == 403
    assert conn.products["p1"]["primary_gtin"] == barcode("871234567890")


def test_equivalent_gtin_alias_cannot_be_reassigned(db):
    conn, _ = db
    # A GTIN-13 recorded under its leading-zero 14-digit variant owns the
    # same identity. A replacement must not create a second Catalogus owner.
    value = barcode("871234567891")
    conn.products["p2"]["primary_gtin"] = "0" + value
    with pytest.raises(HTTPException) as err:
        change(new=value)
    assert err.value.status_code == 409
    assert conn.products["p1"]["primary_gtin"] == barcode("871234567890")
