from app.services.external_database_matchflow_evidence import match_retailer_receipt_line


def test_catalog_candidate_is_deduplicated():
    result = match_retailer_receipt_line("lidl", "Mexicaanse kruiden", True)
    assert result["candidates"]
    assert result["candidates"][0]["score"] >= 0.90
    codes = [str(candidate.get("candidate_source_product_code") or "") for candidate in result["candidates"]]
    assert codes.count("21175") <= 1


def test_data_seed_candidates_have_visible_codes():
    examples = ["courgette", "zoete aardappel"]
    for text in examples:
        result = match_retailer_receipt_line("lidl", text, True)
        assert result["candidates"]
        top = result["candidates"][0]
        assert top["candidate_source_product_code"] not in {"", "unknown"}
        assert top["retailer_article_number"] not in {"", "unknown"}
