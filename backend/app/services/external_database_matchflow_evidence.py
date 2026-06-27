from __future__ import annotations

from typing import Any

from app.services import external_product_candidate_store as candidate_store
from app.services.external_candidate_normalization import normalize_external_candidates
from app.services.external_database_matchers import match_retailer_receipt_line as _base_match_retailer_receipt_line
from app.services.product_evidence_packet import apply_product_evidence_to_candidates, build_product_evidence_packet_dict

MIN_VISIBLE_CANDIDATE_SCORE = 0.70
VISIBLE_CANDIDATE_STATUSES = {
    "possible_candidate",
    "probable_candidate",
    "linked_to_catalog",
    "user_confirmed",
    "external_database_override",
}


def _candidate_score(candidate: dict[str, Any]) -> float:
    try:
        return float(candidate.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_visible_candidate(candidate: dict[str, Any]) -> bool:
    """Generieke kwaliteitsgrens voor kandidaatartikelen.

    Dit bevat nadrukkelijk geen artikelinhoudelijke kennis. Kandidaten onder de
    minimumscore blijven diagnostisch mogelijk, maar worden niet als bruikbaar
    kandidaatartikel opgeslagen/getoond in de reguliere matchflow.
    """
    status = str(candidate.get("candidate_status") or candidate.get("status") or "").strip().lower()
    if status in VISIBLE_CANDIDATE_STATUSES:
        return _candidate_score(candidate) >= MIN_VISIBLE_CANDIDATE_SCORE or status in {
            "linked_to_catalog",
            "user_confirmed",
            "external_database_override",
        }
    return _candidate_score(candidate) >= MIN_VISIBLE_CANDIDATE_SCORE


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
    visible = [candidate for candidate in normalized if _is_visible_candidate(candidate)]

    enriched = dict(result)
    enriched["candidates"] = visible[:5]
    enriched["uses_product_evidence_scoring"] = True
    enriched["uses_candidate_deduplication"] = len(normalized) < len(rescored)
    enriched["uses_visible_candidate_score_filter"] = True
    enriched["minimum_visible_candidate_score"] = MIN_VISIBLE_CANDIDATE_SCORE
    enriched["candidate_count_before_deduplication"] = len(rescored)
    enriched["candidate_count_after_deduplication"] = len(normalized)
    enriched["candidate_count_after_score_filter"] = len(visible[:5])
    enriched["suppressed_weak_candidate_count"] = max(0, len(normalized) - len(visible))
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
