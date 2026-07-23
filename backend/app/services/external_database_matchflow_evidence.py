from __future__ import annotations

from typing import Any

from app.receipt_ingestion.spaarzegels_terms import is_spaarzegels_flow_excluded, is_spaarzegels_financial_context
from app.services import external_product_candidate_store as candidate_store
from app.services.external_candidate_normalization import normalize_external_candidates
from app.services.external_database_matchers import (
    candidate_status_for_score,
    normalize_match_text,
)
from app.services.external_database_off_index_matchers import (
    match_retailer_receipt_line as _base_match_retailer_receipt_line,
)
from app.services.product_evidence_packet import apply_product_evidence_to_candidates, build_product_evidence_packet_dict
from app.services.product_intent_classifier import classify_product_intent
from app.services.product_taxonomy_store import normalize_taxonomy_text

STRONG_CONTAINMENT_MIN_SCORE = 0.70
STRONG_CONTAINMENT_TEXT_SCORE = 0.92
STRONG_CONTAINMENT_MIN_TOKEN_COUNT = 1
TAXONOMY_INTENT_MATCH_MIN_SCORE = 0.70


def _candidate_score(candidate: dict[str, Any]) -> float:
    try:
        return float(candidate.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _meaningful_tokens(value: str) -> set[str]:
    return {token for token in normalize_match_text(value).split() if len(token) >= 3}


def _is_valid_gtin(value: Any) -> bool:
    normalized = str(value or "").strip()
    return bool(normalized.isdigit() and len(normalized) in {8, 12, 13, 14})


def _item_has_known_gtin(item: dict[str, Any]) -> bool:
    return any(
        _is_valid_gtin(item.get(field))
        for field in (
            "gtin",
            "ean",
            "barcode",
            "retailer_article_number",
            "external_article_code",
        )
    )


def _candidate_source_code(candidate: dict[str, Any]) -> str:
    for key in ("candidate_source_product_code", "source_product_code", "code", "retailer_article_number"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value
    return ""


def _candidate_intent(candidate: dict[str, Any]) -> str:
    explicit_intent = str(candidate.get("candidate_product_intent") or candidate.get("product_intent") or "").strip()
    if explicit_intent:
        return explicit_intent

    source_code = _candidate_source_code(candidate)
    if ":" in source_code:
        return source_code.split(":", 1)[1].strip()
    return ""


def _text_overlap(receipt_line_text: str, candidate_name: str) -> tuple[bool, float, list[str]]:
    receipt_normalized = normalize_match_text(receipt_line_text)
    candidate_normalized = normalize_match_text(candidate_name)
    if not receipt_normalized or not candidate_normalized:
        return False, 0.0, []

    receipt_tokens = _meaningful_tokens(receipt_normalized)
    candidate_tokens = _meaningful_tokens(candidate_normalized)
    if len(receipt_tokens) < STRONG_CONTAINMENT_MIN_TOKEN_COUNT or not candidate_tokens:
        return False, 0.0, []

    overlap = receipt_tokens & candidate_tokens
    receipt_overlap = len(overlap) / max(1, len(receipt_tokens))
    candidate_overlap = len(overlap) / max(1, len(candidate_tokens))
    contains_text = receipt_normalized in candidate_normalized or candidate_normalized in receipt_normalized

    strong = bool(
        contains_text
        or receipt_overlap >= 0.95
        or (receipt_overlap >= 0.80 and candidate_overlap >= 0.50)
    )
    return strong, max(receipt_overlap, candidate_overlap), sorted(overlap)


def _apply_strong_text_containment_boost(
    candidates: list[dict[str, Any]],
    receipt_line_text: str,
) -> list[dict[str, Any]]:
    boosted: list[dict[str, Any]] = []
    for candidate in candidates:
        next_candidate = dict(candidate)
        candidate_name = str(next_candidate.get("candidate_name") or "").strip()
        strong, overlap_score, overlap_tokens = _text_overlap(receipt_line_text, candidate_name)
        current_score = _candidate_score(next_candidate)

        if strong and current_score < STRONG_CONTAINMENT_MIN_SCORE:
            next_candidate["score"] = STRONG_CONTAINMENT_MIN_SCORE
            next_candidate["candidate_status"] = candidate_status_for_score(STRONG_CONTAINMENT_MIN_SCORE)
            next_candidate["is_probable"] = STRONG_CONTAINMENT_MIN_SCORE >= 0.85
            next_candidate["strong_text_containment_boost_applied"] = True
            next_candidate["strong_text_containment_overlap_score"] = round(overlap_score, 3)
            next_candidate["strong_text_containment_overlap_tokens"] = overlap_tokens
            breakdown = dict(next_candidate.get("score_breakdown") or {})
            breakdown["strong_text_containment_score"] = STRONG_CONTAINMENT_MIN_SCORE
            breakdown["strong_text_containment_overlap_score"] = round(overlap_score, 3)
            next_candidate["score_breakdown"] = breakdown
        else:
            next_candidate["strong_text_containment_boost_applied"] = False

        boosted.append(next_candidate)
    return boosted


def _apply_taxonomy_intent_match_boost(
    candidates: list[dict[str, Any]],
    receipt_line_text: str,
    retailer_code: str,
) -> list[dict[str, Any]]:
    receipt_intent = classify_product_intent(receipt_line_text, retailer_code=retailer_code)
    if not receipt_intent:
        return candidates

    boosted: list[dict[str, Any]] = []
    for candidate in candidates:
        next_candidate = dict(candidate)
        candidate_intent = _candidate_intent(next_candidate)
        current_score = _candidate_score(next_candidate)
        if candidate_intent == receipt_intent and current_score < TAXONOMY_INTENT_MATCH_MIN_SCORE:
            next_candidate["score"] = TAXONOMY_INTENT_MATCH_MIN_SCORE
            next_candidate["candidate_status"] = candidate_status_for_score(TAXONOMY_INTENT_MATCH_MIN_SCORE)
            next_candidate["is_probable"] = TAXONOMY_INTENT_MATCH_MIN_SCORE >= 0.85
            next_candidate["taxonomy_intent_match_boost_applied"] = True
            next_candidate["taxonomy_intent_match_key"] = receipt_intent
            breakdown = dict(next_candidate.get("score_breakdown") or {})
            breakdown["taxonomy_intent_match_score"] = TAXONOMY_INTENT_MATCH_MIN_SCORE
            next_candidate["score_breakdown"] = breakdown
        else:
            next_candidate["taxonomy_intent_match_boost_applied"] = False
        boosted.append(next_candidate)
    return boosted


def _with_evidence_scoring(result: dict[str, Any], receipt_line_text: str, retailer_code: str) -> dict[str, Any]:
    candidates = list(result.get("candidates") or [])
    if not candidates:
        return result

    evidence_packet = build_product_evidence_packet_dict(receipt_line_text, retailer_code=retailer_code)
    rescored = apply_product_evidence_to_candidates(
        receipt_line_text,
        retailer_code,
        candidates,
        evidence_packet=evidence_packet,
    )
    normalized = normalize_external_candidates(rescored, evidence_packet=evidence_packet)
    boosted = _apply_strong_text_containment_boost(normalized, receipt_line_text)
    boosted = _apply_taxonomy_intent_match_boost(boosted, receipt_line_text, normalize_taxonomy_text(retailer_code))
    boosted.sort(key=lambda candidate: (-_candidate_score(candidate), str(candidate.get("candidate_name") or "")))

    enriched = dict(result)
    enriched["candidates"] = boosted[:5]
    enriched["uses_product_evidence_scoring"] = True
    enriched["uses_candidate_deduplication"] = len(normalized) < len(rescored)
    enriched["uses_strong_text_containment_boost"] = any(
        bool(candidate.get("strong_text_containment_boost_applied"))
        for candidate in boosted
    )
    enriched["uses_taxonomy_intent_match_boost"] = any(
        bool(candidate.get("taxonomy_intent_match_boost_applied"))
        for candidate in boosted
    )
    enriched["strong_text_containment_min_score"] = STRONG_CONTAINMENT_MIN_SCORE
    enriched["taxonomy_intent_match_min_score"] = TAXONOMY_INTENT_MATCH_MIN_SCORE
    enriched["candidate_count_before_deduplication"] = len(rescored)
    enriched["candidate_count_after_deduplication"] = len(normalized[:5])
    enriched["creates_global_product"] = False
    enriched["creates_household_article"] = False
    enriched["creates_inventory_event"] = False
    return enriched


def _external_matching_blocked_result(retailer_code: str, receipt_line_text: str) -> dict[str, Any]:
    return {
        "ok": True,
        "retailer_code": retailer_code,
        "receipt_line_text": receipt_line_text,
        "candidates": [],
        "candidate_count": 0,
        "processed": 0,
        "saved_count": 0,
        "updated_count": 0,
        "skipped_count": 1,
        "external_matching_allowed": False,
        "excluded_from_external_database": True,
        "exclusion_reason": "spaarzegels_financial_line",
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def _item_allows_external_matching(item: dict[str, Any]) -> bool:
    return not is_spaarzegels_flow_excluded(item) and not _item_has_known_gtin(item)


def _filter_external_matching_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [dict(item) for item in items if isinstance(item, dict) and _item_allows_external_matching(item)]


def match_retailer_receipt_line(retailer_code: str, receipt_line_text: str, include_below_threshold: bool = True) -> dict[str, Any]:
    if is_spaarzegels_financial_context(receipt_line_text):
        return _external_matching_blocked_result(retailer_code, receipt_line_text)
    result = _base_match_retailer_receipt_line(
        retailer_code=retailer_code,
        receipt_line_text=receipt_line_text,
        include_below_threshold=include_below_threshold,
    )
    return _with_evidence_scoring(result, receipt_line_text, retailer_code)


def save_matchpreview_candidates(*args: Any, **kwargs: Any) -> dict[str, Any]:
    previous_matcher = candidate_store.match_retailer_receipt_line
    candidate_store.match_retailer_receipt_line = match_retailer_receipt_line
    try:
        if "items" in kwargs:
            kwargs = dict(kwargs)
            kwargs["items"] = _filter_external_matching_items(kwargs.get("items"))
        return candidate_store.save_matchpreview_candidates(*args, **kwargs)
    finally:
        candidate_store.match_retailer_receipt_line = previous_matcher


def ensure_external_receipt_item_candidates(*args: Any, **kwargs: Any) -> dict[str, Any]:
    previous_matcher = candidate_store.match_retailer_receipt_line
    candidate_store.match_retailer_receipt_line = match_retailer_receipt_line
    try:
        if "items" in kwargs:
            kwargs = dict(kwargs)
            original_items = kwargs.get("items")
            filtered_items = _filter_external_matching_items(original_items)
            kwargs["items"] = filtered_items
            result = candidate_store.ensure_external_receipt_item_candidates(*args, **kwargs)
            if isinstance(original_items, list):
                result = dict(result)
                excluded_count = len(original_items) - len(filtered_items)
                spaarzegels_count = len([
                    item for item in original_items
                    if isinstance(item, dict) and is_spaarzegels_flow_excluded(item)
                ])
                known_gtin_count = len([
                    item for item in original_items
                    if isinstance(item, dict) and _item_has_known_gtin(item)
                ])
                result["spaarzegels_excluded_count"] = spaarzegels_count
                result["known_gtin_excluded_count"] = known_gtin_count
                result["external_matching_excluded_count"] = excluded_count
                result["external_matching_guardrail"] = "spaarzegels_and_known_gtin_rows_excluded"
            return result
        return candidate_store.ensure_external_receipt_item_candidates(*args, **kwargs)
    finally:
        candidate_store.match_retailer_receipt_line = previous_matcher
