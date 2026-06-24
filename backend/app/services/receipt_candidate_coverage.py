from __future__ import annotations

from typing import Any

from app.services.receipt_product_intent_analyzer import analyze_receipt_product_line
from app.services.product_taxonomy_store import normalize_taxonomy_text

FALLBACK_SCORE = 0.35
UNRESOLVED_SCORE = 0.10



def _candidate_display_name(receipt_line_text: str | None, analysis) -> str:
    raw_text = str(receipt_line_text or "").strip()
    if analysis.product_type:
        parts = [*analysis.variant_terms, analysis.product_type, analysis.quantity_label]
        display = " ".join(part for part in parts if part).strip()
        return display or raw_text or "Onbekend extern artikel"
    return f"Onbekend extern artikel: {raw_text or 'lege bonregel'}"



def _build_retailer_catalog_candidate(analysis) -> dict[str, Any] | None:
    catalog_match = dict(analysis.retailer_catalog_match or {})
    if not catalog_match.get("matched"):
        return None

    score = round(float(catalog_match.get("confidence") or 0.0), 3)
    candidate_name = str(catalog_match.get("catalog_product_name") or "").strip()
    source_product_code = str(catalog_match.get("source_product_code") or "").strip()
    source_name = str(catalog_match.get("source_name") or "lidl_catalog_enrichment").strip()

    return {
        "candidate_name": candidate_name or _candidate_display_name(analysis.raw_text, analysis),
        "candidate_brand": str(catalog_match.get("brand") or "").strip(),
        "candidate_source_name": source_name,
        "candidate_source_product_code": source_product_code or "unknown",
        "source_name": source_name,
        "source_product_code": source_product_code or "unknown",
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
        "created_by": "m2c2i11_lidl_catalog_enrichment",
    }



def build_receipt_fallback_candidate(receipt_line_text: str | None, retailer_code: str | None = None) -> dict[str, Any]:
    """Maak een veilige kandidaat op basis van catalogusverrijking of bonregel.

    M2C2i-11b: als een retailer-catalogusmatch bestaat, wordt die eerst als
    zichtbare externe/cataloguskandidaat getoond. Alleen wanneer er geen
    catalogusmatch is, valt Rezzerv terug op de onzekere bonregel-fallback.
    De kandidaat mag nooit automatisch een global product, Mijn artikel of
    voorraadmutatie aanmaken.
    """
    analysis = analyze_receipt_product_line(receipt_line_text, retailer_code=retailer_code)
    catalog_candidate = _build_retailer_catalog_candidate(analysis)
    if catalog_candidate:
        return catalog_candidate

    has_intent = bool(analysis.product_intent)
    score = FALLBACK_SCORE if has_intent else UNRESOLVED_SCORE
    status = "fallback_candidate" if has_intent else "unresolved_candidate"
    source_name = "receipt_product_intent_fallback" if has_intent else "receipt_unresolved_fallback"

    return {
        "candidate_name": _candidate_display_name(receipt_line_text, analysis),
        "candidate_brand": "",
        "candidate_source_name": source_name,
        "candidate_source_product_code": f"fallback:{analysis.normalized_text or 'empty'}",
        "source_name": source_name,
        "source_product_code": f"fallback:{analysis.normalized_text or 'empty'}",
        "retailer_article_number": "",
        "quantity_label": analysis.quantity_label,
        "variant": " ".join(analysis.variant_terms),
        "source_url": "",
        "score": score,
        "score_breakdown": {
            "text_score": 0.0,
            "brand_score": 0.0,
            "product_type_score": 0.35 if has_intent else 0.0,
            "quantity_score": 0.35 if analysis.quantity_label else 0.0,
            "variant_score": 0.35 if analysis.variant_terms else 0.0,
            "source_score": 0.10,
            "intent_score": 1.0 if has_intent else 0.0,
            "fallback_score": score,
        },
        "receipt_product_intent": analysis.product_intent,
        "candidate_product_intent": analysis.product_intent,
        "candidate_category": analysis.category,
        "candidate_product_type": analysis.product_type,
        "intent_score": 1.0 if has_intent else 0.0,
        "has_meaningful_intent_match": True,
        "candidate_status": status,
        "is_probable": False,
        "is_user_confirmed": False,
        "is_external_database_override": False,
        "requires_user_confirmation": True,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "created_by": "m2c2i9b_receipt_candidate_coverage",
    }



def ensure_candidate_coverage(match_result: dict[str, Any], receipt_line_text: str | None, retailer_code: str | None = None) -> dict[str, Any]:
    """Garandeer dat een match-resultaat minimaal één kandidaat bevat."""
    candidates = list(match_result.get("candidates") or [])
    if candidates:
        return match_result

    normalized_retailer = normalize_taxonomy_text(retailer_code or match_result.get("retailer_code"))
    fallback_candidate = build_receipt_fallback_candidate(receipt_line_text, retailer_code=normalized_retailer)
    result = dict(match_result)
    result["retailer_code"] = normalized_retailer
    result["receipt_line_text"] = str(receipt_line_text or result.get("receipt_line_text") or "")
    result["candidates"] = [fallback_candidate]
    result["candidate_source"] = fallback_candidate["candidate_source_name"]
    result["uses_coverage_fallback"] = fallback_candidate.get("candidate_status") in {"fallback_candidate", "unresolved_candidate"}
    result["uses_legacy_fallback"] = False
    result["creates_global_product"] = False
    result["creates_household_article"] = False
    result["creates_inventory_event"] = False
    return result
