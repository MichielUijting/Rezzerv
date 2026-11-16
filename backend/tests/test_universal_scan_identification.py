"""Universal scanner: explicit Catalogus confirmation without household mutations."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.services.barcode_identity_service import calculate_gtin_check_digit, lookup_gtin
from app.services.universal_scan_identification_service import (
    UniversalScanIdentityError, confirm_scanned_catalog_gtin,
)


def gtin(body):
    return body + str(calculate_gtin_check_digit(body))


@pytest.fixture
def database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE global_products (
              id TEXT PRIMARY KEY, primary_gtin TEXT UNIQUE, name TEXT,
              brand TEXT, variant TEXT, category TEXT, size_value REAL,
              size_unit TEXT, product_fingerprint TEXT, source TEXT,
              status TEXT, image_url TEXT, created_at TEXT, updated_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE product_identities (
              id TEXT PRIMARY KEY, household_article_id TEXT,
              global_product_id TEXT, identity_type TEXT, identity_value TEXT,
              source TEXT, confidence_score REAL, is_primary BOOLEAN,
              created_at TEXT, updated_at TEXT
            )
        """))
        conn.execute(text("CREATE TABLE inventory_events (id TEXT PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE household_articles (id TEXT PRIMARY KEY, naam TEXT)"))
        conn.execute(text("INSERT INTO household_articles VALUES ('existing', 'Melk')"))
    yield engine
    engine.dispose()


def test_register_explicit_gtin_without_receipt_household_or_stock(database):
    value = gtin("871234567890")
    with database.begin() as conn:
        result = confirm_scanned_catalog_gtin(conn, barcode=value, product_name=" Melk  1 liter ")
        assert result["status"] == "created"
        assert result["stock_changes"] == result["receipt_changes"] == result["household_changes"] == 0
        assert result["product"]["name"] == "Melk 1 liter"
        lookup = lookup_gtin(conn, value)
        assert lookup["match_status"] == "matched"
        assert lookup["product"]["global_product_id"] == result["product"]["global_product_id"]
        assert conn.execute(text("SELECT COUNT(*) FROM product_identities")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM household_articles")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one() == 1


def test_repeat_is_idempotent_and_does_not_rename(database):
    value = gtin("871234567890")
    with database.begin() as conn:
        first = confirm_scanned_catalog_gtin(conn, barcode=value, product_name="Melk")
        again = confirm_scanned_catalog_gtin(conn, barcode=value, product_name="Andere naam")
        assert again["saved"] is False
        assert again["status"] == "already_known"
        assert again["product"]["global_product_id"] == first["product"]["global_product_id"]
        assert conn.execute(text("SELECT name FROM global_products")).scalar_one() == "Melk"
        assert conn.execute(text("SELECT COUNT(*) FROM product_identities")).scalar_one() == 1


@pytest.mark.parametrize("code,name", [
    ("123", "Melk"),
    (gtin("201234567890"), "Winkelcode"),
    (gtin("871234567890"), ""),
    (gtin("871234567890"), "x" * 201),
])
def test_invalid_restricted_and_missing_name_fail_closed(database, code, name):
    with database.begin() as conn:
        with pytest.raises(UniversalScanIdentityError):
            confirm_scanned_catalog_gtin(conn, barcode=code, product_name=name)
        assert conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one() == 0


def test_incomplete_existing_product_requires_manual_review(database):
    value = gtin("871234567890")
    with database.begin() as conn:
        conn.execute(text("""
            INSERT INTO global_products (id, primary_gtin, name, status)
            VALUES ('legacy', :gtin, 'Oude naam', 'active')
        """), {"gtin": value})
        with pytest.raises(UniversalScanIdentityError) as exc:
            confirm_scanned_catalog_gtin(conn, barcode=value, product_name="Nieuwe naam")
        assert exc.value.status_code == 409
        assert conn.execute(text("SELECT name FROM global_products")).scalar_one() == "Oude naam"
        assert conn.execute(text("SELECT COUNT(*) FROM product_identities")).scalar_one() == 0


def test_route_denies_unprivileged_user_before_any_database_write(database, monkeypatch):
    from fastapi import HTTPException
    from app.api import barcode_routes

    value = gtin("871234567890")
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
            {"gtin": value, "product_name": "Melk"}, authorization=None
        )
    assert exc.value.status_code == 403
    with database.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one() == 0


def test_authorized_route_requires_canonical_platform_permission(database, monkeypatch):
    from app.api import barcode_routes

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
    with database.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM household_articles")).scalar_one() == 1


def test_equivalent_gtin_thirteen_fourteen_cannot_create_second_catalog_owner(database):
    thirteen = gtin("871234567890")
    fourteen = "0" + thirteen
    with database.begin() as conn:
        first = confirm_scanned_catalog_gtin(conn, barcode=thirteen, product_name="Melk")
        with pytest.raises(UniversalScanIdentityError) as exc:
            confirm_scanned_catalog_gtin(conn, barcode=fourteen, product_name="Nieuwe melk")
        assert exc.value.status_code == 409
        assert conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM product_identities")).scalar_one() == 1
        assert conn.execute(text("SELECT id FROM global_products")).scalar_one() == first["product"]["global_product_id"]
