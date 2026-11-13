"""Fase 1: barcode-scope en classificatie-onafhankelijke herkenning.

Read-only fakes cover lookup decisions without creating a SQLite database.
PostgreSQL shared-stack authority remains the full-stack test owner.
"""
import pytest

import app.services.barcode_identity_service as barcode_service
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


class _ReadOnlyRows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _CatalogReadOnlyConnection:
    """Only SELECT is permitted; no schema, receipt, stock or identity writes."""

    def __init__(self, *, gtin, has_identity=True, active=True, ambiguous=False):
        self.gtin = gtin
        self.has_identity = has_identity
        self.active = active
        self.ambiguous = ambiguous
        self.requests = []

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        assert sql.upper().startswith("SELECT "), sql
        self.requests.append(sql)
        if "FROM global_products gp" in sql and "ORDER BY CASE" in sql:
            row = {
                "id": "p1", "name": "Courgette", "brand": "AH",
                "status": "active" if self.active else "inactive",
                "primary_gtin": self.gtin,
                "identity_id": "i1" if self.has_identity else None,
                "identity_source": "manual" if self.has_identity else None,
                "identity_is_primary": self.has_identity,
                "has_matching_gtin_identity": int(self.has_identity),
                "product_type_key": None, "gpc_brick_code": None,
                "product_type_name": None, "has_active_official_gpc": 0,
            }
            return _ReadOnlyRows([row, {**row, "id": "p2"}] if self.ambiguous else [row])
        if "SELECT DISTINCT gp.id" in sql and "FROM global_products gp" in sql:
            return _ReadOnlyRows(["p1"])
        raise AssertionError("Unrecognized read-only SQL: " + sql)


@pytest.mark.parametrize("value", [
    "2008234600001",
    _gtin("020123456789"),
    _gtin("201234567890"),
    _gtin("291234567890"),
    _gtin("0200823460000"),  # GTIN-14 indicator 0 + 20 restricted prefix
    _gtin("21234567890"),  # UPC-A expanded as 021...
])
def test_restricted_codes_require_retailer_scope(value):
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


def test_confirmed_gtin_matches_without_gpc_classification(monkeypatch):
    gtin = "8722800072026"
    conn = _CatalogReadOnlyConnection(gtin=gtin)
    monkeypatch.setattr(barcode_service, "_table_names",
                        lambda _conn: {"global_products", "product_identities"})
    result = lookup_gtin(conn, gtin)
    assert result["match_status"] == "matched", result
    assert result["quality"]["official_gpc_active"] is False
    assert result["product"]["global_product_id"] == "p1"
    assert result["mutated"] is False
    assert resolve_catalog_identity(conn, gtin=gtin)["status"] == "matched"
    assert conn.requests and all(q.startswith("SELECT ") for q in conn.requests)


def test_unknown_or_mismatched_identity_stays_incomplete(monkeypatch):
    gtin = "8722800072026"
    conn = _CatalogReadOnlyConnection(gtin=gtin, has_identity=False)
    monkeypatch.setattr(barcode_service, "_table_names",
                        lambda _conn: {"global_products", "product_identities"})
    result = lookup_gtin(conn, gtin)
    assert result["match_status"] == "incomplete"
    assert result["quality"]["identity_consistent"] is False


def test_ambiguous_gtin_owner_is_not_automatically_used(monkeypatch):
    gtin = "8722800072026"
    conn = _CatalogReadOnlyConnection(gtin=gtin, ambiguous=True)
    monkeypatch.setattr(barcode_service, "_table_names",
                        lambda _conn: {"global_products", "product_identities"})
    assert lookup_gtin(conn, gtin)["match_status"] == "conflict"


def test_restricted_barcode_cannot_be_saved_as_new_global_product():
    with pytest.raises(BarcodeHouseholdArticleLinkError) as error:
        save_gtin_catalog_and_household_link(
            object(), household_id="household-x", purchase_import_line_id="line-x",
            household_article_id="article-x", gtin="2008234600001",
            article_name="Courgette",
        )
    assert error.value.status_code == 409
    assert "Identificeren" in error.value.detail
