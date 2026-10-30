"""Shared catalog GTIN writes are permissioned, validated and household-independent."""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.api import catalog_routes
from app.services.barcode_identity_service import calculate_gtin_check_digit


@pytest.fixture
def catalog_db(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE global_products ("
            "id TEXT PRIMARY KEY, status TEXT, primary_gtin TEXT, updated_at TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE product_identities ("
            "id TEXT PRIMARY KEY, identity_type TEXT, identity_value TEXT, global_product_id TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE household_articles (id TEXT PRIMARY KEY, household_id TEXT, global_product_id TEXT, barcode TEXT)"
        ))
        conn.execute(text("INSERT INTO global_products VALUES ('p1', 'active', NULL, NULL)"))
        conn.execute(text("INSERT INTO global_products VALUES ('p2', 'active', NULL, NULL)"))
        conn.execute(text("INSERT INTO household_articles VALUES ('a1', 'h1', 'p1', NULL)"))
        conn.execute(text("INSERT INTO household_articles VALUES ('a2', 'h2', 'p1', NULL)"))

    monkeypatch.setattr(catalog_routes, "engine", engine)
    monkeypatch.setattr(
        catalog_routes, "_tables",
        lambda: {"global_products", "product_identities", "household_articles"},
    )
    monkeypatch.setattr(catalog_routes, "_columns", lambda name: {
        "global_products": {"id", "status", "primary_gtin", "updated_at"},
        "product_identities": {"id", "identity_type", "identity_value", "global_product_id"},
    }.get(name, set()))
    checked = []
    monkeypatch.setattr(
        catalog_routes,
        "require_platform_permission_from_session",
        lambda key: checked.append(key),
    )
    yield engine, checked
    engine.dispose()


def gtin(body="871234567890"):
    return body + str(calculate_gtin_check_digit(body))


def write(product_id, value):
    return catalog_routes.set_catalog_primary_gtin(
        product_id, catalog_routes.CatalogGtinUpdateRequest(gtin=value),
    )


def test_shared_gtin_saved_without_modifying_any_household_stock(catalog_db):
    engine, checked = catalog_db
    saved = write("p1", gtin())
    assert saved == {"global_product_id": "p1", "gtin": gtin(), "changed": True}
    assert checked == ["platform.catalog.update"]
    with engine.begin() as conn:
        product = conn.execute(text(
            "SELECT primary_gtin FROM global_products WHERE id = 'p1'"
        )).scalar_one()
        articles = conn.execute(text(
            "SELECT household_id, barcode FROM household_articles ORDER BY id"
        )).all()
        assert product == gtin()
        assert articles == [("h1", None), ("h2", None)]
    repeated = write("p1", gtin())
    assert repeated["changed"] is False


def test_invalid_gtin_rejected_without_write(catalog_db):
    engine, _ = catalog_db
    with pytest.raises(HTTPException) as error:
        write("p1", "12345")
    assert error.value.status_code == 422
    with engine.begin() as conn:
        assert conn.execute(text(
            "SELECT primary_gtin FROM global_products WHERE id = 'p1'"
        )).scalar_one() is None


def test_duplicate_gtin_cannot_be_given_to_another_catalog_product(catalog_db):
    write("p1", gtin())
    with pytest.raises(HTTPException) as error:
        write("p2", gtin())
    assert error.value.status_code == 409


def test_linked_identity_on_another_product_blocks_assignment(catalog_db):
    engine, _ = catalog_db
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO product_identities VALUES ('i1', 'gtin', :gtin, 'p2')"
        ), {"gtin": gtin()})
    with pytest.raises(HTTPException) as error:
        write("p1", gtin())
    assert error.value.status_code == 409


def test_existing_primary_cannot_be_silently_replaced(catalog_db):
    write("p1", gtin())
    with pytest.raises(HTTPException) as error:
        write("p1", gtin("871234567899"))
    assert error.value.status_code == 409


def test_unknown_or_deleted_product_not_changed(catalog_db):
    engine, _ = catalog_db
    with pytest.raises(HTTPException) as error:
        write("missing", gtin())
    assert error.value.status_code == 404
    with engine.begin() as conn:
        conn.execute(text("UPDATE global_products SET status='deleted' WHERE id='p1'"))
    with pytest.raises(HTTPException) as error:
        write("p1", gtin())
    assert error.value.status_code == 404


def test_server_authorization_runs_before_database_mutation(catalog_db, monkeypatch):
    engine, _ = catalog_db
    def deny(_permission):
        raise HTTPException(status_code=403, detail="Geen rechten")
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session", deny)
    with pytest.raises(HTTPException) as error:
        write("p1", gtin())
    assert error.value.status_code == 403
    with engine.begin() as conn:
        assert conn.execute(text(
            "SELECT primary_gtin FROM global_products WHERE id='p1'"
        )).scalar_one() is None
