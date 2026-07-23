from __future__ import annotations

from typing import Any

from app.services.receipt_product_intent_analyzer import analyze_receipt_product_line
from app.services.product_taxonomy_store import normalize_taxonomy_text


def _build_retailer_catalog_candidate(analysis) -> dict[str, Any] | None:
    """Bouw alleen kandidaten uit echte retailer/cataloguskennis.

    M2C2i-19S: fallback-kandidaten op basis van alleen de bonregeltekst zijn
    expliciet niet toegestaan. Geen catalogusmatch betekent geen kandidaat.
    """
    catalog_match = dict(analysis.retailer_catalog_match or {})
    if not catalog_match.get("matched"):
        return None

    score = round(float(catalog_match.get("confidence") or 0.0), 3)
    candidate_name = str(catalog_match.get("catalog_product_name") or "").strip()
    source_product_code = str(catalog_match.get("source_product_code") or "").strip()
    source_name = str(catalog_match.get("source_name") or "lidl_catalog_enrichment").strip()

    return {
        "candidate_name": candidate_name,
        "candidate_brand": str(catalog_match.get("brand") or "").strip(),
        "candidate_source_name": source_name,
        "candidate_source_product_code": source_product_code,
        "source_name": source_name,
        "source_product_code": source_product_code,
        "retailer_article_number": source_product_code,
        "quantity_label": str(catalog_match.get("quantity_label") or analysis.quantity_label or "").strip(),
        "variant": " ".join(analysis.variant_terms),
        "source_url": str(catalog_match.get("source_url") or "").strip(),
        "score": score,
        "score_breakdown": {
            "text_score": 0.90,
            "brand_score": 0.90 if catalog_match.get("brand") else 0.60,
            "product_type_score": 1.0 if analysis.product_intent else 0.70,
            "quantity_score": 0.85 if catalog_match.get("quantity_label") or analysis.quantity_label else 0.45,
            "variant_score": 0.85 if analysis.variant_terms else 0.70,
            "source_score": score,
            "intent_score": 1.0 if analysis.product_intent else 0.70,
            "catalog_enrichment_score": score,
        },
        "receipt_product_intent": analysis.product_intent,
        "candidate_product_intent": analysis.product_intent,
        "candidate_category": analysis.category or str(catalog_match.get("category") or "").strip().lower(),
        "candidate_product_type": analysis.product_type or str(catalog_match.get("product_type") or "").strip().lower(),
        "intent_score": 1.0 if analysis.product_intent else 0.70,
        "has_meaningful_intent_match": True,
        "candidate_status": "probable_candidate" if score >= 0.85 else "possible_candidate",
        "is_probable": score >= 0.85,
        "is_user_confirmed": False,
        "is_external_database_override": False,
        "requires_user_confirmation": False,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "created_by": "m2c2i19s_real_catalog_candidate",
    }


def build_receipt_fallback_candidate(receipt_line_text: str | None, retailer_code: str | None = None) -> dict[str, Any] | None:
    """Compatibility wrapper: retourneert alleen echte cataloguskandidaten.

    De oude betekenis van deze functie was: maak altijd minimaal één fallback-
    kandidaat. Dat principe is verworpen. Deze wrapper blijft bestaan om imports
    niet te breken, maar geeft ``None`` terug wanneer er geen echte match is.
    """
    analysis = analyze_receipt_product_line(receipt_line_text, retailer_code=retailer_code)
    return _build_retailer_catalog_candidate(analysis)


def ensure_candidate_coverage(match_result: dict[str, Any], receipt_line_text: str | None, retailer_code: str | None = None) -> dict[str, Any]:
    """Verrijk alleen met echte cataloguskandidaat; nooit met fallback.

    M2C2i-19S: onbekend zonder echte externe/cataloguskennis blijft onbekend.
    """
    candidates = list(match_result.get("candidates") or [])
    if candidates:
        result = dict(match_result)
        result["uses_coverage_fallback"] = False
        return result

    normalized_retailer = normalize_taxonomy_text(retailer_code or match_result.get("retailer_code"))
    catalog_candidate = build_receipt_fallback_candidate(receipt_line_text, retailer_code=normalized_retailer)
    result = dict(match_result)
    result["retailer_code"] = normalized_retailer
    result["receipt_line_text"] = str(receipt_line_text or result.get("receipt_line_text") or "")

    if catalog_candidate:
        result["candidates"] = [catalog_candidate]
        result["candidate_source"] = catalog_candidate["candidate_source_name"]
        result["uses_coverage_fallback"] = False
    else:
        result["candidates"] = []
        result["candidate_source"] = "no_real_candidate"
        result["uses_coverage_fallback"] = False
        result["no_candidate_reason"] = "no_real_external_or_catalog_match"

    result["uses_legacy_fallback"] = False
    result["creates_global_product"] = False
    result["creates_household_article"] = False
    result["creates_inventory_event"] = False
    return result
