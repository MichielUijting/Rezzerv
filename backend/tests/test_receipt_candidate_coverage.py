from app.services.receipt_candidate_coverage import build_receipt_fallback_candidate, ensure_candidate_coverage



def test_builds_fallback_candidate_for_known_product_intent_without_catalog_match():
    candidate = build_receipt_fallback_candidate("ITALIAANSE RASP KAAS 200G", retailer_code="jumbo")

    assert candidate["candidate_status"] == "fallback_candidate"
    assert candidate["candidate_source_name"] == "receipt_product_intent_fallback"
    assert candidate["receipt_product_intent"] == "zuivel.kaas"
    assert candidate["candidate_category"] == "zuivel"
    assert candidate["candidate_product_type"] == "kaas"
    assert candidate["quantity_label"] == "200 g"
    assert candidate["requires_user_confirmation"] is True
    assert candidate["creates_global_product"] is False
    assert candidate["creates_household_article"] is False
    assert candidate["creates_inventory_event"] is False



def test_builds_visible_lidl_catalog_candidate_before_fallback():
    candidate = build_receipt_fallback_candidate("Mexicaanse kruidenm.", retailer_code="lidl")

    assert candidate["candidate_status"] == "probable_candidate"
    assert candidate["candidate_source_name"] == "lidl_catalog_enrichment"
    assert candidate["candidate_source_product_code"] == "21175"
    assert candidate["candidate_name"] == "Kania Mexicaanse kruidenmix"
    assert candidate["candidate_brand"] == "Kania/Kanig"
    assert candidate["is_probable"] is True
    assert candidate["requires_user_confirmation"] is False
    assert candidate["creates_global_product"] is False
    assert candidate["creates_household_article"] is False
    assert candidate["creates_inventory_event"] is False



def test_builds_unresolved_candidate_for_unknown_product_intent():
    candidate = build_receipt_fallback_candidate("ONBEKEND ARTIKEL X9", retailer_code="lidl")

    assert candidate["candidate_status"] == "unresolved_candidate"
    assert candidate["candidate_source_name"] == "receipt_unresolved_fallback"
    assert candidate["candidate_name"] == "Onbekend extern artikel: ONBEKEND ARTIKEL X9"
    assert candidate["receipt_product_intent"] == ""
    assert candidate["requires_user_confirmation"] is True
    assert candidate["score"] == 0.10



def test_ensure_candidate_coverage_preserves_existing_candidates():
    existing = {
        "retailer_code": "lidl",
        "receipt_line_text": "HALFVOLLE MELK",
        "candidates": [{"candidate_name": "Lidl Zuivel Halfvolle melk"}],
        "candidate_source": "external_product_index",
    }

    covered = ensure_candidate_coverage(existing, "HALFVOLLE MELK", retailer_code="lidl")

    assert covered["candidates"] == [{"candidate_name": "Lidl Zuivel Halfvolle melk"}]
    assert covered["candidate_source"] == "external_product_index"



def test_ensure_candidate_coverage_adds_single_fallback_when_empty():
    empty = {
        "retailer_code": "lidl",
        "receipt_line_text": "ONBEKEND ARTIKEL X9",
        "candidates": [],
        "candidate_source": "external_product_index_no_match",
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }

    covered = ensure_candidate_coverage(empty, "ONBEKEND ARTIKEL X9", retailer_code="lidl")

    assert len(covered["candidates"]) == 1
    assert covered["candidates"][0]["candidate_status"] == "unresolved_candidate"
    assert covered["candidate_source"] == "receipt_unresolved_fallback"
    assert covered["uses_coverage_fallback"] is True
    assert covered["creates_global_product"] is False
    assert covered["creates_household_article"] is False
    assert covered["creates_inventory_event"] is False



def test_ensure_candidate_coverage_uses_lidl_catalog_candidate_when_available():
    empty = {
        "retailer_code": "lidl",
        "receipt_line_text": "Mexicaanse kruidenm.",
        "candidates": [],
        "candidate_source": "external_product_index_no_match",
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }

    covered = ensure_candidate_coverage(empty, "Mexicaanse kruidenm.", retailer_code="lidl")

    assert len(covered["candidates"]) == 1
    assert covered["candidate_source"] == "lidl_catalog_enrichment"
    assert covered["uses_coverage_fallback"] is False
    assert covered["candidates"][0]["candidate_name"] == "Kania Mexicaanse kruidenmix"
    assert covered["candidates"][0]["candidate_status"] == "probable_candidate"
    assert covered["creates_global_product"] is False
    assert covered["creates_household_article"] is False
    assert covered["creates_inventory_event"] is False
