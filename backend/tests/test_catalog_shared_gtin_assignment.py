"""Isolated shared GTIN route contracts; no SQLite or application data writes."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import catalog_routes
from app.services.barcode_identity_service import calculate_gtin_check_digit


class FakeResult:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class FakeCatalogConnection:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.products = {
            "p1": {"id": "p1", "status": "active", "primary_gtin": None},
            "p2": {"id": "p2", "status": "active", "primary_gtin": None},
        }
        self.identities = []
        self.household_articles = [
            {"id": "a1", "household_id": "h1", "global_product_id": "p1", "barcode": None},
            {"id": "a2", "household_id": "h2", "global_product_id": "p1", "barcode": None},
        ]
        self.inventory_events = []

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        params = params or {}
        if sql.startswith("SELECT pg_advisory_xact_lock"):
            return FakeResult([(1,)])
        if sql.startswith("SELECT id, status, primary_gtin FROM global_products"):
            item = self.products.get(params["product_id"])
            return FakeResult([dict(item)] if item else [])
        if sql.startswith("SELECT id FROM global_products WHERE primary_gtin ="):
            matches = [
                {"id": row["id"]} for row in self.products.values()
                if row["id"] != params["product_id"] and row["primary_gtin"] == params["gtin"]
            ]
            return FakeResult(matches[:1])
        if sql.startswith("SELECT id FROM product_identities"):
            matches = [
                {"id": item["id"]} for item in self.identities
                if item["identity_value"] == params["gtin"]
                and item["identity_type"] in {"gtin", "ean", "upc"}
                and item["global_product_id"] is not None
                and item["global_product_id"] != params["product_id"]
            ]
            return FakeResult(matches[:1])
        if sql.startswith("UPDATE global_products SET primary_gtin ="):
            product = self.products[params["product_id"]]
            if not product["primary_gtin"]:
                product["primary_gtin"] = params["gtin"]
            return FakeResult()
        raise AssertionError(f"Onverwachte SQL: {sql}")


class FakeEngine:
    def __init__(self):
        self.conn = FakeCatalogConnection()

    @contextmanager
    def begin(self):
        yield self.conn


@pytest.fixture
def catalog_db(monkeypatch):
    engine = FakeEngine()
    checked = []
    household_checks = []
    monkeypatch.setattr(catalog_routes, "engine", engine)
    monkeypatch.setattr(
        catalog_routes, "_tables",
        lambda: {"global_products", "product_identities", "household_articles"},
    )
    monkeypatch.setattr(catalog_routes, "_columns", lambda table: {
        "global_products": {"id", "status", "primary_gtin", "updated_at"},
        "product_identities": {"id", "identity_type", "identity_value", "global_product_id"},
    }.get(table, set()))
    monkeypatch.setattr(
        catalog_routes, "require_platform_permission_from_session",
        lambda key: checked.append(key),
    )
    monkeypatch.setattr(
        catalog_routes, "require_household_admin_from_session",
        lambda: household_checks.append(True),
    )
    return engine.conn, checked, household_checks


def gtin(body="871234567890"):
    return body + str(calculate_gtin_check_digit(body))


def write(product_id, value):
    return catalog_routes.set_catalog_primary_gtin(
        product_id, catalog_routes.CatalogGtinUpdateRequest(gtin=value),
    )


def test_shared_gtin_saved_without_modifying_any_household_stock(catalog_db):
    conn, checked, household_checks = catalog_db
    before = [dict(item) for item in conn.household_articles]
    assert write("p1", gtin()) == {
        "global_product_id": "p1", "gtin": gtin(), "changed": True,
    }
    assert checked == ["platform.catalog.update"]
    assert not household_checks
    assert conn.products["p1"]["primary_gtin"] == gtin()
    assert conn.household_articles == before
    assert conn.inventory_events == []
    assert write("p1", gtin())["changed"] is False


def test_invalid_gtin_rejected_without_write(catalog_db):
    conn, _, _ = catalog_db
    with pytest.raises(HTTPException) as error:
        write("p1", "12345")
    assert error.value.status_code == 422
    assert conn.products["p1"]["primary_gtin"] is None


def test_duplicate_gtin_cannot_be_given_to_another_catalog_product(catalog_db):
    write("p1", gtin())
    with pytest.raises(HTTPException) as error:
        write("p2", gtin())
    assert error.value.status_code == 409


def test_linked_identity_on_another_product_blocks_assignment(catalog_db):
    conn, _, _ = catalog_db
    conn.identities.append({
        "id": "i1", "identity_type": "gtin", "identity_value": gtin(),
        "global_product_id": "p2",
    })
    with pytest.raises(HTTPException) as error:
        write("p1", gtin())
    assert error.value.status_code == 409


def test_existing_primary_cannot_be_silently_replaced(catalog_db):
    write("p1", gtin())
    with pytest.raises(HTTPException) as error:
        write("p1", gtin("871234567899"))
    assert error.value.status_code == 409


def test_unknown_or_deleted_product_not_changed(catalog_db):
    conn, _, _ = catalog_db
    with pytest.raises(HTTPException) as error:
        write("missing", gtin())
    assert error.value.status_code == 404
    conn.products["p1"]["status"] = "deleted"
    with pytest.raises(HTTPException) as error:
        write("p1", gtin())
    assert error.value.status_code == 404


def test_household_owner_has_narrow_add_only_fallback(catalog_db, monkeypatch):
    conn, platform_checks, household_checks = catalog_db

    def no_platform_access(_permission):
        platform_checks.append("denied")
        raise HTTPException(status_code=403, detail="Geen platformrechten")

    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session", no_platform_access)
    assert write("p1", gtin())["changed"] is True
    assert platform_checks == ["denied"]
    assert household_checks == [True]
    assert conn.products["p1"]["primary_gtin"] == gtin()


def test_non_admin_cannot_modify_catalog(catalog_db, monkeypatch):
    conn, _, _ = catalog_db

    def no_platform_access(_permission):
        raise HTTPException(status_code=403, detail="Geen platformrechten")

    def no_household_access():
        raise HTTPException(status_code=403, detail="Geen huishoudbeheerdersrechten")

    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session", no_platform_access)
    monkeypatch.setattr(catalog_routes, "require_household_admin_from_session", no_household_access)
    with pytest.raises(HTTPException) as error:
        write("p1", gtin())
    assert error.value.status_code == 403
    assert conn.products["p1"]["primary_gtin"] is None


def test_other_platform_auth_errors_do_not_grant_household_fallback(catalog_db, monkeypatch):
    def broken_session(_permission):
        raise HTTPException(status_code=401, detail="Sessie ontbreekt")

    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session", broken_session)
    with pytest.raises(HTTPException) as error:
        write("p1", gtin())
    assert error.value.status_code == 401
