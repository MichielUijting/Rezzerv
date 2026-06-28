from __future__ import annotations

import re
from typing import Any

from app.services.external_database_matchers import (
    POSSIBLE_CANDIDATE_THRESHOLD,
    PROBABLE_CANDIDATE_THRESHOLD,
    SCORE_WEIGHTS,
    candidate_status_for_score,
    normalize_match_text,
    _text_similarity,
)
from app.services.external_product_index_store import search_external_product_index_candidates
from app.services.product_intent_classifier import (
    classify_product_intent,
    has_meaningful_product_intent_match,
    product_intent_match_score,
)


def _value(row: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _numeric_tokens(value: str) -> set[str]:
    return set(re.findall(r"\d+(?:[,.]\d+)?", normalize_match_text(value)))


def _token_overlap_score(left: str, right: str) -> float:
    left_tokens = {token for token in normalize_match_text(left).split() if len(token) >= 3}
    right_tokens = {token for token in normalize_match_text(right).split() if len(token) >= 3}
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens & right_tokens
    return len(overlap) / max(1, len(left_tokens | right_tokens))


def _score_off_index_candidate(receipt_line_text: str, row: dict[str, Any]) -> dict[str, Any]:
    product_name = _value(row, ["product_name", "name", "generic_name"])
    brand = _value(row, ["brand", "brands"])
    quantity_label = _value(row, ["quantity", "net_content", "packaging"])
    category = _value(row, ["category", "categories"])
    source_name = _value(row, ["source_name"]) or "OFF-index"
    source_product_code = _value(row, ["source_product_code", "gtin", "ean", "code"]) or "unknown"
    source_url = _value(row, ["source_url", "url", "product_url"])

    candidate_intent_text = " ".join(part for part in [product_name, category] if part)
    receipt_product_intent = classify_product_intent(receipt_line_text)
    candidate_product_intent = classify_product_intent(candidate_intent_text)
    intent_score = product_intent_match_score(receipt_line_text, candidate_intent_text)
    has_meaningful_intent_match = has_meaningful_product_intent_match(receipt_line_text, candidate_intent_text)

    text_score = max(
        _text_similarity(receipt_line_text, product_name),
        _token_overlap_score(receipt_line_text, product_name),
    )

    normalized_receipt = normalize_match_text(receipt_line_text)
    normalized_brand = normalize_match_text(brand)
    brand_score = 1.0 if normalized_brand and normalized_brand in normalized_receipt else (0.60 if brand else 0.40)

    receipt_numbers = _numeric_tokens(receipt_line_text)
    quantity_numbers = _numeric_tokens(quantity_label)
    quantity_score = 1.0 if receipt_numbers and quantity_numbers and receipt_numbers & quantity_numbers else (0.65 if quantity_label else 0.45)

    normalized_code = normalize_match_text(source_product_code)
    code_score = 1.0 if normalized_code and normalized_code in normalized_receipt else (0.55 if source_product_code != "unknown" else 0.35)

    category_score = max(0.45, _token_overlap_score(receipt_line_text, category)) if category else 0.40
    source_score = 0.92 if source_name == "OFF-index" else 0.80

    breakdown = {
        "text_score": round(text_score, 3),
        "brand_score": round(brand_score, 3),
        "product_type_score": round(category_score, 3),
        "quantity_score": round(quantity_score, 3),
        "variant_score": 0.70,
        "source_score": round(source_score, 3),
        "code_score": round(code_score, 3),
        "category_score": round(category_score, 3),
        "intent_score": round(intent_score, 3),
    }

    base_score = sum(breakdown[key] * SCORE_WEIGHTS[key] for key in SCORE_WEIGHTS)
    score = min(1.0, base_score + (code_score * 0.08) + (category_score * 0.04))
    score = round(score * intent_score, 3)

    return {
        "candidate_name": product_name or source_product_code,
        "candidate_brand": brand,
        "candidate_source_name": source_name,
        "candidate_source_product_code": source_product_code,
        "source_name": source_name,
        "source_product_code": source_product_code,
        "retailer_article_number": source_product_code,
        "quantity_label": quantity_label,
        "variant": category,
        "source_url": source_url,
        "score": score,
        "score_breakdown": breakdown,
        "receipt_product_intent": receipt_product_intent,
        "candidate_product_intent": candidate_product_intent,
        "intent_score": round(intent_score, 3),
        "has_meaningful_intent_match": has_meaningful_intent_match,
        "candidate_status": candidate_status_for_score(score),
        "is_probable": score >= PROBABLE_CANDIDATE_THRESHOLD,
        "is_user_confirmed": False,
        "is_external_database_override": False,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "created_by": "external_database_off_index_matcher_v3_no_taxonomy_seed",
    }


def match_retailer_receipt_line(retailer_code: str, receipt_line_text: str, include_below_threshold: bool = True) -> dict[str, Any]:
    """Match against real OFF index rows only; never emit product taxonomy seed candidates."""
    normalized_retailer = normalize_match_text(retailer_code)
    receipt_product_intent = classify_product_intent(receipt_line_text)

    index_rows = search_external_product_index_candidates(
        receipt_line_text,
        limit=120,
        retailer_code=normalized_retailer,
        additional_search_terms=[],
    )

    scored = [_score_off_index_candidate(receipt_line_text, row) for row in index_rows]

    if receipt_product_intent:
        scored = [
            candidate
            for candidate in scored
            if candidate.get("candidate_product_intent") == receipt_product_intent
        ]
    else:
        scored = [
            candidate
            for candidate in scored
            if candidate.get("has_meaningful_intent_match", True)
        ]

    if not include_below_threshold:
        scored = [candidate for candidate in scored if candidate["score"] >= PROBABLE_CANDIDATE_THRESHOLD]

    scored.sort(key=lambda item: (-item["score"], item["candidate_name"]))
    scored = scored[:5]

    candidate_source = "external_product_index" if scored else "external_product_index_no_match"
    return {
        "retailer_code": normalized_retailer,
        "receipt_line_text": receipt_line_text,
        "expanded_terms": [normalize_match_text(receipt_line_text)],
        "off_query_terms": [],
        "retailer_article_codes": [],
        "retailer_article_code_analysis": [],
        "index_search_terms": [normalize_match_text(receipt_line_text)],
        "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
        "possible_candidate_threshold": POSSIBLE_CANDIDATE_THRESHOLD,
        "candidates": scored,
        "candidate_source": candidate_source,
        "uses_legacy_fallback": False,
        "uses_coverage_fallback": False,
        "uses_retailer_taxonomy_preview": False,
        "uses_product_taxonomy_seed_candidates": False,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
