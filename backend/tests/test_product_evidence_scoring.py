from app.services.product_evidence_packet import build_product_evidence_packet_dict, score_candidate_with_product_evidence


def test_evidence_scoring_boosts_matching_off_candidate_without_gtin_cap():
    packet = build_product_evidence_packet_dict("Mexicaanse kruiden", retailer_code="lidl")
    candidate = {
        "candidate_name": "Kania Mexicaanse kruidenmix",
        "candidate_brand": "Kania",
        "candidate_source_product_code": "unknown-off-code",
        "quantity_label": "25 g",
        "score": 0.62,
        "candidate_status": "weak_candidate",
        "is_probable": False,
        "score_breakdown": {},
    }

    scored = score_candidate_with_product_evidence(candidate, packet)

    assert scored["score"] == 0.82
    assert scored["product_evidence_boost_applied"] is True
    assert scored["product_evidence_score"] >= 0.55
    assert scored["is_probable"] is False
    assert scored["creates_global_product"] is False
    assert scored["creates_household_article"] is False
    assert scored["creates_inventory_event"] is False


def test_evidence_scoring_promotes_exact_retailer_article_code_to_probable():
    packet = build_product_evidence_packet_dict("Mexicaanse kruiden", retailer_code="lidl")
    candidate = {
        "candidate_name": "Kania Mexicaanse kruidenmix",
        "candidate_brand": "Kania",
        "candidate_source_product_code": "21175",
        "quantity_label": "25 g",
        "score": 0.62,
        "candidate_status": "weak_candidate",
        "is_probable": False,
        "score_breakdown": {},
    }

    scored = score_candidate_with_product_evidence(candidate, packet)

    assert scored["score"] == 0.95
    assert scored["candidate_status"] == "probable_candidate"
    assert scored["is_probable"] is True
    assert scored["product_evidence_boost_applied"] is True
