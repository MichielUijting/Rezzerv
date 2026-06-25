from __future__ import annotations

import json

from app.services.retailer_catalog_enrichment import CATALOG_SEED_PATH, enrich_receipt_product_line_dict


def _rules() -> list[dict]:
    payload = json.loads(CATALOG_SEED_PATH.read_text(encoding="utf-8"))
    return [dict(rule) for rule in payload.get("rules") or []]


def test_m2c2i18_lidl_catalog_seed_has_expanded_coverage() -> None:
    rules = _rules()

    assert len(rules) >= 25
    for rule in rules:
        assert rule.get("receipt_terms")
        assert str(rule.get("source_product_code") or "").strip()
        assert str(rule.get("catalog_product_name") or "").strip()
        assert str(rule.get("category") or "").strip()
        assert str(rule.get("product_type") or "").strip()
        assert float(rule.get("confidence") or 0.0) >= 0.80


def test_m2c2i18_all_seed_receipt_terms_can_enrich() -> None:
    for rule in _rules():
        source_code = str(rule.get("source_product_code") or "").strip()
        for term in rule.get("receipt_terms") or []:
            result = enrich_receipt_product_line_dict("lidl", str(term), include_below_threshold=True)
            assert result, term
            assert result["candidate_source_product_code"] == source_code
            assert result["creates_global_product"] is False
            assert result["creates_household_article"] is False
            assert result["creates_inventory_event"] is False
