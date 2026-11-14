"""Regression: a known Catalogus barcode never creates a name-based second article.

The barcode-purchase endpoint resides in the legacy monolithic main.py. Test
its identity choice explicitly until it is moved behind a dedicated service.
"""
from pathlib import Path


def _barcode_purchase_route() -> str:
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(
        encoding="utf-8"
    )
    start = source.index('@app.post("/api/purchases/barcode")')
    end = source.index("@app.", start + 1)
    return source[start:end]


def test_catalog_product_match_reuses_exact_existing_household_id():
    route = _barcode_purchase_route()
    assert "option_id = ensure_household_article_for_global_product(" in route
    assert "if resolved_global_product_id and option_id:" in route
    assert "article_id = str(option_id)" in route
    assert "canonical_article = get_household_article_row_by_id(conn, household_id, article_id)" in route
    assert "article_name = normalize_household_article_name(canonical_article.get('naam'))" in route
    assert "else:\n            article_id = ensure_household_article(conn, household_id, article_name)" in route
    # Never use the name-based constructor when a canonical household ID exists.
    assert route.index("article_id = str(option_id)") < route.index(
        "article_id = ensure_household_article(conn, household_id, article_name)"
    )


def test_conflicting_or_disappeared_household_link_stops_before_stock_write():
    route = _barcode_purchase_route()
    assert "if not canonical_article:" in route
    assert "linked_product_id != resolved_global_product_id" in route
    assert route.index("linked_product_id != resolved_global_product_id") < route.index(
        "apply_inventory_purchase_by_identity("
    )
    assert "raise HTTPException(status_code=409" in route


def test_receipt_global_product_reuses_existing_household_id():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(
        encoding="utf-8"
    )
    start = source.index("def resolve_receipt_line_product_links(")
    end = source.index("\ndef backfill_purchase_import_live_aliases(", start)
    route = source[start:end]
    assert "existing_household_article = find_household_article_for_global_product(" in route
    assert "resolved_article_option_id = str(existing_household_article.get('id'))" in route
    assert "and not resolved_article_option_id:" in route
