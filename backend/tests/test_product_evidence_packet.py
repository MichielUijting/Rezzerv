from app.services.product_evidence_packet import build_product_evidence_packet_dict


def test_lidl_mexican_herbs_evidence_packet_contains_catalog_identity():
    packet = build_product_evidence_packet_dict("Mexicaanse kruiden", retailer_code="lidl")

    assert packet["matched"] is True
    assert packet["retailer_code"] == "lidl"
    assert packet["retailer"] == "Lidl"
    assert packet["retailer_article_code"] == "21175"
    assert packet["canonical_name"] == "Kania Mexicaanse kruidenmix"
    assert packet["brand"] == "Kania/Kanig"
    assert packet["brand_terms"] == ["Kania", "Kanig"]
    assert packet["category"] == "Kruiden"
    assert packet["product_type"] == "Specerijenmix"
    assert packet["quantity_label"] == "25-35 g"
    assert packet["gtin"] is None
    assert "gtin" in packet["missing_evidence_fields"]
    assert "ingredients_text" in packet["missing_evidence_fields"]
    assert "nutrition_text" in packet["missing_evidence_fields"]
    assert packet["off_score_signals"]["has_retailer_catalog_match"] is True
    assert packet["off_score_signals"]["has_brand"] is True
    assert packet["off_score_signals"]["has_quantity"] is True
    assert packet["off_score_signals"]["has_gtin"] is False
    assert packet["recommended_next_action"] == "scan_package_for_gtin"
    assert packet["creates_global_product"] is False
    assert packet["creates_household_article"] is False
    assert packet["creates_inventory_event"] is False


def test_lidl_mexican_herbs_evidence_packet_builds_off_query_terms():
    packet = build_product_evidence_packet_dict("Mexicaanse kruidenm.", retailer_code="lidl")

    assert "kania mexicaanse kruidenmix" in packet["off_query_terms"]
    assert "kania" in packet["off_query_terms"]
    assert "kanig" in packet["off_query_terms"]
    assert "kruiden" in packet["off_query_terms"]
    assert "specerijenmix" in packet["off_query_terms"]
    assert "25 35 g" in packet["off_query_terms"]


def test_unknown_lidl_line_evidence_packet_stays_safe():
    packet = build_product_evidence_packet_dict("Onbekend Lidl artikel", retailer_code="lidl")

    assert packet["matched"] is False
    assert packet["evidence_sources"] == ["receipt"]
    assert packet["retailer_article_code"] == ""
    assert packet["gtin"] is None
    assert packet["recommended_next_action"] == "scan_package_for_gtin"
    assert packet["creates_global_product"] is False
    assert packet["creates_household_article"] is False
    assert packet["creates_inventory_event"] is False
