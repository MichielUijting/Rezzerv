"""Targeted receipt/stock shared-authority tests (no runtime/database mutation)."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.services.receipt_stock_review_service import (
    checked_stock_quantity,
    find_confirmed_household_article_id,
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
