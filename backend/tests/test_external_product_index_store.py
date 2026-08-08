from app.services.external_product_index_store import _fixture_rows, fixture_brand_for_row


def test_lidl_off_fixture_rows_are_brand_diverse_without_brand_whitelist():
    rows = [
        row
        for row in _fixture_rows()
        if row["retailer_code"] == "lidl" and row["source_name"] == "OFF-index"
    ]

    brands = {row["brand"] for row in rows}

    assert rows
    assert len(brands) > 1
    assert "Kania" not in brands


def test_lidl_fixture_brand_is_category_derived_not_single_retailer_brand():
    assert fixture_brand_for_row("lidl", "Lidl", "Zuivel") == "Lidl Zuivel"
    assert fixture_brand_for_row("lidl", "Lidl", "Pasta") == "Lidl Pasta"
    assert fixture_brand_for_row("lidl", "Lidl", "Zuivel") != fixture_brand_for_row("lidl", "Lidl", "Pasta")


def test_lidl_fixture_rows_keep_product_terms_searchable():
    row = next(
        item
        for item in _fixture_rows()
        if item["retailer_code"] == "lidl" and item["source_product_code"] == "LIDL-00001"
    )

    assert row["product_name"] == "Lidl Zuivel Halfvolle melk"
    assert "halfvolle melk" in row["normalized_search_text"]
    assert "lidl" in row["normalized_search_text"]
    assert row["brand"] == "Lidl Zuivel"
