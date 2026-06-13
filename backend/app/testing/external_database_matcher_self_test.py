from __future__ import annotations

from app.services.external_database_matchers import match_retailer_receipt_line


def run_external_database_matcher_self_test() -> dict:
    mexican = match_retailer_receipt_line("lidl", "Mexicaanse kruidenm.", include_below_threshold=False)
    mexican_candidates = mexican.get("candidates") or []
    assert len(mexican_candidates) == 3, "Mexicaanse kruidenm. moet drie waarschijnlijke Lidl-variantkandidaten geven"
    assert {item["retailer_article_number"] for item in mexican_candidates} == {"21175"}
    assert all(item["score"] >= 0.85 for item in mexican_candidates)
    assert all(item["candidate_status"] == "probable_candidate" for item in mexican_candidates)
    assert all(item["external_database_can_override"] is True for item in mexican_candidates)
    assert mexican.get("creates_global_product") is False
    assert mexican.get("creates_household_article") is False

    taco_sauce = match_retailer_receipt_line("lidl", "Taco saus", include_below_threshold=False)
    sauce_candidates = taco_sauce.get("candidates") or []
    assert sauce_candidates, "Taco saus moet minimaal een waarschijnlijke Lidl-kandidaat geven"
    assert sauce_candidates[0]["retailer_article_number"] in {"20122386", "20122393"}
    assert sauce_candidates[0]["score"] >= 0.85

    return {
        "status": "passed",
        "mexican_candidate_count": len(mexican_candidates),
        "mexican_retailer_article_numbers": sorted({item["retailer_article_number"] for item in mexican_candidates}),
        "taco_sauce_top_candidate": sauce_candidates[0]["candidate_name"],
        "taco_sauce_top_score": sauce_candidates[0]["score"],
        "creates_global_product": False,
        "creates_household_article": False,
    }


if __name__ == "__main__":
    print(run_external_database_matcher_self_test())
