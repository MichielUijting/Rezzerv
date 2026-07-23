from app.services import external_database_matchers as matcher



def test_matcher_guarantees_unresolved_candidate_when_lidl_index_has_no_match(monkeypatch):
    monkeypatch.setattr(matcher, "search_external_product_index_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        matcher,
        "analyze_retailer_article_codes",
        lambda *args, **kwargs: {
            "retailer_article_codes": [],
            "retailer_article_code_analysis": [],
            "off_query_terms": [],
            "index_search_terms": [],
        },
    )

    result = matcher.match_retailer_receipt_line("lidl", "ONBEKEND ARTIKEL X9")

    assert len(result["candidates"]) == 1
    assert result["candidate_source"] == "receipt_unresolved_fallback"
    assert result["candidates"][0]["candidate_status"] == "unresolved_candidate"
    assert result["candidates"][0]["requires_user_confirmation"] is True
    assert result["creates_global_product"] is False
    assert result["creates_household_article"] is False
    assert result["creates_inventory_event"] is False



def test_matcher_guarantees_fallback_candidate_when_known_intent_has_no_catalog_match(monkeypatch):
    monkeypatch.setattr(matcher, "search_external_product_index_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        matcher,
        "analyze_retailer_article_codes",
        lambda *args, **kwargs: {
            "retailer_article_codes": [],
            "retailer_article_code_analysis": [],
            "off_query_terms": [],
            "index_search_terms": [],
        },
    )

    result = matcher.match_retailer_receipt_line("lidl", "ITALIAANSE RASP KAAS 200G")

    assert len(result["candidates"]) == 1
    assert result["candidate_source"] == "receipt_product_intent_fallback"
    assert result["candidates"][0]["candidate_status"] == "fallback_candidate"
    assert result["candidates"][0]["receipt_product_intent"] == "zuivel.kaas"
    assert result["candidates"][0]["candidate_product_type"] == "kaas"
    assert result["candidates"][0]["requires_user_confirmation"] is True
    assert result["creates_global_product"] is False
    assert result["creates_household_article"] is False
    assert result["creates_inventory_event"] is False



def test_matcher_surfaces_lidl_catalog_candidate_when_index_has_no_match(monkeypatch):
    monkeypatch.setattr(matcher, "search_external_product_index_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        matcher,
        "analyze_retailer_article_codes",
        lambda *args, **kwargs: {
            "retailer_article_codes": [],
            "retailer_article_code_analysis": [],
            "off_query_terms": [],
            "index_search_terms": [],
        },
    )

    result = matcher.match_retailer_receipt_line("lidl", "Mexicaanse kruidenm.")

    assert len(result["candidates"]) == 1
    assert result["candidate_source"] == "lidl_catalog_enrichment"
    assert result["uses_coverage_fallback"] is False
    assert result["candidates"][0]["candidate_name"] == "Kania Mexicaanse kruidenmix"
    assert result["candidates"][0]["candidate_source_product_code"] == "21175"
    assert result["candidates"][0]["candidate_status"] == "probable_candidate"
    assert result["candidates"][0]["requires_user_confirmation"] is False
    assert result["creates_global_product"] is False
    assert result["creates_household_article"] is False
    assert result["creates_inventory_event"] is False
