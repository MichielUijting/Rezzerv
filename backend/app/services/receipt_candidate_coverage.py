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


def build_receipt_fallback_candidate(receipt_line_text: str | None, retailer_code: str | None = None) -> dict[str, Any]:
    """Maak een veilige fallback-kandidaat op basis van alleen de bonregel.

    M2C2i-9b: deze kandidaat voorkomt lege kandidaatlijsten, maar blijft altijd
    onzeker en vraagt altijd gebruikerbevestiging. De kandidaat mag nooit een
    global product, Mijn artikel of voorraadmutatie aanmaken.
    """
    analysis = analyze_receipt_product_line(receipt_line_text, retailer_code=retailer_code)
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
    result["uses_coverage_fallback"] = True
    result["uses_legacy_fallback"] = False
    result["creates_global_product"] = False
    result["creates_household_article"] = False
    result["creates_inventory_event"] = False
    return result
