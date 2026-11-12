"""Fase 1: barcode-scope en classificatie-onafhankelijke herkenning.

Only disposable SQLite fixtures are used. No real receipt/household/stock data.
"""
import pytest
from sqlalchemy import create_engine, text

from app.services.barcode_scope_service import classify_barcode_scope
from app.services.barcode_identity_service import (
    BarcodeHouseholdArticleLinkError,
    calculate_gtin_check_digit,
    lookup_gtin,
    save_gtin_catalog_and_household_link,
    validate_barcode,
)
from app.services.catalog_identity_resolution_service import resolve_catalog_identity


def _gtin(body):
    return body + str(calculate_gtin_check_digit(body))


@pytest.mark.parametrize("value", [
    "2008234600001",
    _gtin("020123456789"),
    _gtin("201234567890"),
    _gtin("291234567890"),
    "02008234600001",  # a GTIN-14 with 0 indicator and restricted 20 prefix
    _gtin("21234567890"),  # UPC-A expanded as 021...
])
def test_restricted_codes_require_retailer_scope(value):
    if value == "02008234600001":  # use its prefix only; checksum is not asserted here
        pass
    result = classify_barcode_scope(value)
    assert result["scope"] == "restricted", result
    assert result["requires_retailer"] is True


def test_regular_gtin_is_only_a_global_candidate_not_proof():
    gtin = "8722800072026"
    assert validate_barcode(gtin)["valid"] is True
    assert classify_barcode_scope(gtin)["scope"] == "global_candidate"
    assert validate_barcode(gtin)["barcode_scope"] == "global_candidate"
    assert classify_barcode_scope("abc")["scope"] == "invalid"


@pytest.mark.parametrize("value", [
    "2008234600001",
    _gtin("020123456789"),
])
def test_restricted_codes_cannot_be_looked_up_globally_without_db(value):
    class ForbidDatabaseReads:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("Restricted code caused an unsafe global DB query")
    assert lookup_gtin(ForbidDatabaseReads(), value)["match_status"] == "scope_required"
    assert resolve_catalog_identity(ForbidDatabaseReads(), gtin=value)["status"] == "scope_required"


def test_confirmed_gtin_matches_without_gpc_classification():
    gtin = "8722800072026"
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE global_products (id TEXT PRIMARY KEY, name TEXT, brand TEXT, "
            "status TEXT, primary_gtin TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE product_identities (id TEXT PRIMARY KEY, global_product_id TEXT, "
            "identity_type TEXT, identity_value TEXT, source TEXT, is_primary INTEGER)"
        ))
        conn.execute(text(
            "INSERT INTO global_products VALUES ('p1', 'Courgette', 'AH', 'active', :gtin)"
        ), {"gtin": gtin})
        conn.execute(text(
            "INSERT INTO product_identities VALUES "
            "('i1', 'p1', 'gtin', :gtin, 'manual', 1)"
        ), {"gtin": gtin})
        result = lookup_gtin(conn, gtin)
        assert result["match_status"] == "matched", result
        assert result["quality"]["official_gpc_active"] is False
        assert result["product"]["global_product_id"] == "p1"
        assert result["mutated"] is False
        assert resolve_catalog_identity(conn, gtin=gtin)["status"] == "matched"


def test_unknown_or_mismatched_identity_stays_incomplete():
    gtin = "8722800072026"
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE global_products (id TEXT PRIMARY KEY, name TEXT, brand TEXT, "
            "status TEXT, primary_gtin TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE product_identities (id TEXT PRIMARY KEY, global_product_id TEXT, "
            "identity_type TEXT, identity_value TEXT, source TEXT, is_primary INTEGER)"
        ))
        conn.execute(text(
            "INSERT INTO global_products VALUES ('p1', 'Courgette', NULL, 'active', :gtin)"
        ), {"gtin": gtin})
        result = lookup_gtin(conn, gtin)
        assert result["match_status"] == "incomplete"
        assert result["quality"]["identity_consistent"] is False


def test_restricted_barcode_cannot_be_saved_as_new_global_product():
    with pytest.raises(BarcodeHouseholdArticleLinkError) as error:
        save_gtin_catalog_and_household_link(
            object(), household_id="household-x", purchase_import_line_id="line-x",
            household_article_id="article-x", gtin="2008234600001", article_name="Courgette"
        )
    assert error.value.status_code == 409
    assert "Identificeren" in error.value.detail
