"""Targeted receipt/stock shared-authority tests (no runtime/database mutation)."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.services.receipt_stock_review_service import (
    checked_stock_quantity,
    find_confirmed_household_article_id,
    find_proven_store_sku_household_article_id,
    get_confirmed_store_memory,
    resolve_stock_household_article,
    normalized_store_memory_key,
)
from app.services.receipt_direct_inventory_approval_patch import (
    _validate_direct_receipt_quantities,
)


class Rows:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class FakeConn:
    def __init__(self, *, memory=None, existing=False, receipt_lines=None):
        self.memory = memory
        self.existing = existing
        self.receipt_lines = receipt_lines or []
        self.queries = []

    def execute(self, statement, params):
        sql = " ".join(str(statement).split())
        params = dict(params)
        self.queries.append((sql, params))
        if "FROM store_import_memory" in sql:
            return Rows([self.memory] if self.memory else [])
        if "FROM global_products" in sql:
            return Rows([{"name": "Melk"}])
        if "FROM household_articles" in sql:
            return Rows([{"id": "existing"}] if self.existing else [])
        if "FROM receipt_tables" in sql:
            return Rows([{"store_name": "Winkel"}])
        if "FROM receipt_table_lines" in sql:
            return Rows(self.receipt_lines)
        raise AssertionError("unexpected SQL: " + sql)


def main():
    return SimpleNamespace(
        resolve_review_article_option=lambda conn, article_id, household_id: (
            {"id": article_id} if household_id == "house-1" and article_id == "article-1" else None
        ),
        find_household_article_for_global_product=Mock(return_value={"id": "article-catalog"}),
        ensure_household_article_for_global_product=Mock(return_value="article-catalog"),
        ensure_household_article=Mock(return_value="article-new"),
        normalize_household_article_name=lambda value: str(value or "").strip(),
        derive_receipt_line_semantics=lambda line, store_name: {
            "inventory_eligible": bool(line.get("inventory_eligible")),
        },
    )


@pytest.mark.parametrize(("quantity", "unit", "expected"), [
    (None, "stuk", 0),
    ("", "stuk", 0),
    ("nvt", "stuk", 0),
    ("NaN", "stuk", 0),
    ("inf", "stuk", 0),
    (-1, "stuk", 0),
    (0, "stuk", 0),
    (2.5, "stuk", 0),
    (2, "stuk", 2),
    ("3", "", 3),
    (0.5, "kg", 1),
    (1000, "g", 1),
    (3, "onbekend", 3),
    (6, "10 st 5 l", 6),
    (2.5, "10 st 5 l", 0),
])
def test_single_shared_quantity_authority(quantity, unit, expected):
    assert checked_stock_quantity(quantity, unit) == expected


def test_confirmed_memory_is_scoped_and_reused_by_both_flows():
    conn = FakeConn(memory={
        "article_id": "article-1", "preferred_location_id": "space-1", "times_confirmed": 3,
    })
    found = get_confirmed_store_memory(
        conn, household_id="house-1", store_provider_code="retailer",
        article_name="  MELK ", brand="Winkel",
    )
    assert found["article_id"] == "article-1"
    assert found["times_confirmed"] == 3
    assert conn.queries[0][1] == {
        "household_id": "house-1",
        "store_provider_code": "retailer",
        "normalized_key": normalized_store_memory_key("  MELK ", "Winkel"),
    }
    assert find_confirmed_household_article_id(
        conn, household_id="house-1", store_provider_code="retailer",
        article_name="MELK", brand="Winkel",
    ) == "article-1"


def test_unconfirmed_same_name_is_not_silently_joined_to_existing_article():
    conn = FakeConn(existing=True)
    module = main()
    result = resolve_stock_household_article(
        conn, main_module=module, household_id="house-1",
        line={"article_name_raw": "Melk"}, store_provider_code="retailer",
        allow_new_receipt_article=True,
    )
    assert result is None
    module.ensure_household_article.assert_not_called()


def test_genuinely_new_kassa_article_gets_canonical_id():
    conn = FakeConn(existing=False)
    module = main()
    result = resolve_stock_household_article(
        conn, main_module=module, household_id="house-1",
        line={"article_name_raw": "Melk"}, store_provider_code="retailer",
        allow_new_receipt_article=True,
    )
    assert result == "article-new"
    module.ensure_household_article.assert_called_once_with(conn, "house-1", "Melk")


def test_invalid_explicit_household_id_does_not_fallback_to_name():
    conn = FakeConn()
    module = main()
    assert resolve_stock_household_article(
        conn, main_module=module, household_id="house-1",
        line={"matched_household_article_id": "other-household", "article_name_raw": "Melk"},
        store_provider_code="retailer", allow_new_receipt_article=True,
    ) is None
    assert conn.queries == []
    module.ensure_household_article.assert_not_called()


def test_confirmed_global_product_reuses_canonical_global_resolver():
    conn = FakeConn()
    module = main()
    assert resolve_stock_household_article(
        conn, main_module=module, household_id="house-1",
        line={"matched_global_product_id": "g-1", "article_name_raw": "Melk"},
        store_provider_code="retailer",
    ) == "article-catalog"
    module.find_household_article_for_global_product.assert_called_once()
    module.ensure_household_article_for_global_product.assert_not_called()


def test_catalog_link_cannot_overwrite_existing_same_name_household_article():
    conn = FakeConn(existing=True)
    module = main()
    module.find_household_article_for_global_product.return_value = None
    assert resolve_stock_household_article(
        conn, main_module=module, household_id="house-1",
        line={"matched_global_product_id": "global-1", "article_name_raw": "Melk"},
        store_provider_code="retailer",
    ) is None
    module.ensure_household_article_for_global_product.assert_not_called()


def test_financial_lines_are_excluded_but_missing_stock_quantity_blocks_kassa():
    module = main()
    conn = FakeConn(receipt_lines=[
        {"id": "financial", "inventory_eligible": False, "quantity": None},
        {"id": "stock", "inventory_eligible": True, "quantity": None, "unit": "stuk"},
    ])
    with pytest.raises(HTTPException) as exc:
        _validate_direct_receipt_quantities(module, conn, "receipt-1")
    assert exc.value.status_code == 409
    assert "hoeveelheid" in str(exc.value.detail)


def test_validated_kassa_quantity_passes_before_approval():
    module = main()
    conn = FakeConn(receipt_lines=[
        {"id": "stock", "inventory_eligible": True,
         "quantity": None, "corrected_quantity": 3,
         "unit": "stuk", "corrected_unit": "stuk"},
    ])
    assert _validate_direct_receipt_quantities(module, conn, "receipt-1") is None


def test_proven_lidl_sku_reuses_one_household_identity_across_prices():
    conn = FakeConn(receipt_lines=[
        {"matched_article_id": "milk-1", "raw_label": "Verse halfvolle melk 0,88 B",
         "barcode": None, "global_product_id": None},
        {"matched_article_id": "milk-1", "raw_label": "Verse halfvolle melk 0,99 B",
         "barcode": None, "global_product_id": None},
    ])
    module = main()
    article_id = resolve_stock_household_article(
        conn, main_module=module, household_id="house-1",
        line={"article_name_raw": "Verse halfvolle melk", "retailer_sku": "lidl-213"},
        store_provider_code="lidl", allow_historical_bootstrap=True,
    )
    assert article_id == "milk-1"
    module.ensure_household_article.assert_not_called()
    assert any(sql.startswith("SELECT rtl.matched_article_id") and
               args["retailer_sku"] == "lidl-213" and args["store"] == "lidl"
               and args["household_id"] == "house-1"
               for sql, args in conn.queries)


@pytest.mark.parametrize("rows", [
    [
        {"matched_article_id": "milk-1", "raw_label": "Verse halfvolle melk 0,88 B",
         "barcode": None},
        {"matched_article_id": "different", "raw_label": "Verse halfvolle melk 0,99 B",
         "barcode": None},
    ],
    [
        {"matched_article_id": "milk-1", "raw_label": "Volle melk 0,88 B",
         "barcode": None},
    ],
    [
        {"matched_article_id": "milk-1", "raw_label": "Verse halfvolle melk 0,88 B",
         "barcode": "8712345678906"},
    ],
])
def test_store_sku_does_not_merge_conflicting_identity(rows):
    conn = FakeConn(receipt_lines=rows)
    assert find_proven_store_sku_household_article_id(
        conn, household_id="house-1", store_provider_code="lidl",
        retailer_sku="lidl-213", article_name="Verse halfvolle melk",
        barcode="8712345678913",
    ) is None


def test_unproven_sku_or_cross_household_is_never_article_proof():
    for household_id, provider, sku in (
        ("0", "lidl", "123"), ("house-1", "unknown", "123"),
        ("house-1", "lidl", ""),
    ):
        conn = FakeConn()
        assert find_proven_store_sku_household_article_id(
            conn, household_id=household_id, store_provider_code=provider,
            retailer_sku=sku, article_name="Melk",
        ) is None
        assert not conn.queries


def test_recycled_sku_with_conflicting_valid_gtins_fails_closed_without_new_barcode():
    conn = FakeConn(receipt_lines=[
        {"matched_article_id": "milk-1", "raw_label": "Verse halfvolle melk 0,88 B",
         "barcode": "8712345678906"},
        {"matched_article_id": "milk-1", "raw_label": "Verse halfvolle melk 0,99 B",
         "barcode": "8712345678913"},
    ])
    assert find_proven_store_sku_household_article_id(
        conn, household_id="house-1", store_provider_code="lidl",
        retailer_sku="lidl-213", article_name="Verse halfvolle melk",
    ) is None
