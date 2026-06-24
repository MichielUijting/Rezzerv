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
    evidence_scored = [candidate for candidate in candidates if "product_evidence_score" in candidate]
    assert evidence_scored
    assert evidence_scored[0]["product_evidence_score"] >= 0.0
    assert evidence_scored[0].get("product_evidence_packet", {}).get("matched") is True
    assert all(candidate["creates_global_product"] is False for candidate in candidates)
    assert all(candidate["creates_household_article"] is False for candidate in candidates)
    assert all(candidate["creates_inventory_event"] is False for candidate in candidates)
