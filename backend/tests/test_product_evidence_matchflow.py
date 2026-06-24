from app.services.external_database_matchflow_evidence import match_retailer_receipt_line


def test_matchflow_applies_product_evidence_scoring_to_candidates():
    result = match_retailer_receipt_line(
        retailer_code="lidl",
        receipt_line_text="Mexicaanse kruiden",
        include_below_threshold=True,
    )

    assert result["uses_product_evidence_scoring"] is True
    assert result["creates_global_product"] is False
    assert result["creates_household_article"] is False
    assert result["creates_inventory_event"] is False

    candidates = result["candidates"]
    assert candidates
    boosted = [candidate for candidate in candidates if candidate.get("product_evidence_boost_applied")]
    assert boosted
    assert all(candidate["creates_global_product"] is False for candidate in candidates)
    assert all(candidate["creates_household_article"] is False for candidate in candidates)
    assert all(candidate["creates_inventory_event"] is False for candidate in candidates)
