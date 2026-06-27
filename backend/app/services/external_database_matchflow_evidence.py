from __future__ import annotations

from typing import Any

from app.services import external_product_candidate_store as candidate_store
from app.services.external_candidate_normalization import normalize_external_candidates
from app.services.external_database_matchers import (
    candidate_status_for_score,
    match_retailer_receipt_line as _base_match_retailer_receipt_line,
    normalize_match_text,
)
from app.services.product_evidence_packet import apply_product_evidence_to_candidates, build_product_evidence_packet_dict

STRONG_CONTAINMENT_MIN_SCORE = 0.70
STRONG_CONTAINMENT_TEXT_SCORE = 0.92
STRONG_CONTAINMENT_MIN_TOKEN_COUNT = 1


def _candidate_score(candidate: dict[str, Any]) -> float:
    try:
        return float(candidate.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _meaningful_tokens(value: str) -> set[str]:
    return {token for token in normalize_match_text(value).split() if len(token) >= 3}


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
    boosted.sort(key=lambda candidate: (-_candidate_score(candidate), str(candidate.get("candidate_name") or "")))

    enriched = dict(result)
    enriched["candidates"] = boosted[:5]
    enriched["uses_product_evidence_scoring"] = True
    enriched["uses_candidate_deduplication"] = len(normalized) < len(rescored)
    enriched["uses_strong_text_containment_boost"] = any(
        bool(candidate.get("strong_text_containment_boost_applied"))
        for candidate in boosted
    )
    enriched["strong_text_containment_min_score"] = STRONG_CONTAINMENT_MIN_SCORE
    enriched["candidate_count_before_deduplication"] = len(rescored)
    enriched["candidate_count_after_deduplication"] = len(normalized[:5])
    enriched["creates_global_product"] = False
    enriched["creates_household_article"] = False
    enriched["creates_inventory_event"] = False
    return enriched


def match_retailer_receipt_line(retailer_code: str, receipt_line_text: str, include_below_threshold: bool = True) -> dict[str, Any]:
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
        return candidate_store.save_matchpreview_candidates(*args, **kwargs)
    finally:
        candidate_store.match_retailer_receipt_line = previous_matcher


def ensure_external_receipt_item_candidates(*args: Any, **kwargs: Any) -> dict[str, Any]:
    previous_matcher = candidate_store.match_retailer_receipt_line
    candidate_store.match_retailer_receipt_line = match_retailer_receipt_line
    try:
        return candidate_store.ensure_external_receipt_item_candidates(*args, **kwargs)
    finally:
        candidate_store.match_retailer_receipt_line = previous_matcher
