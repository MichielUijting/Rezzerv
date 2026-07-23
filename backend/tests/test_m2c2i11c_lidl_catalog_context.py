from app.services.external_database_matchers import match_retailer_receipt_line
from app.services.external_retailer_taxonomy import analyze_retailer_article_codes
from app.services.retailer_catalog_enrichment import enrich_receipt_product_line_dict


def test_full_lidl_mexican_herbs_text_resolves_catalog_article_code():
    analysis = analyze_retailer_article_codes("Mexicaanse kruiden", "lidl")

    assert "21175" in analysis["retailer_article_codes"]


def test_full_lidl_mexican_herbs_text_resolves_catalog_enrichment():
    enrichment = enrich_receipt_product_line_dict("Mexicaanse kruiden", retailer_code="lidl")

    assert enrichment["matched"] is True
    assert enrichment["source_product_code"] == "21175"
    assert enrichment["catalog_product_name"] == "Kania Mexicaanse kruidenmix"


def test_full_lidl_mexican_herbs_text_gets_catalog_boost_for_real_receipt_context():
    result = match_retailer_receipt_line("lidl", "Mexicaanse kruiden")
    candidate = result["candidates"][0]

    assert candidate["candidate_name"] == "Kania Mexicaanse kruidenmix"
    assert candidate["candidate_source_product_code"] == "21175"
    assert candidate["score"] >= 0.95
    assert candidate["candidate_status"] == "probable_candidate"
    assert candidate["catalog_boost_applied"] is True
    assert candidate["creates_global_product"] is False
    assert candidate["creates_household_article"] is False
    assert candidate["creates_inventory_event"] is False
