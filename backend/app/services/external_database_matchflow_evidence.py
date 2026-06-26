from __future__ import annotations

from typing import Any

from app.services import external_product_candidate_store as candidate_store
from app.services.external_candidate_normalization import normalize_external_candidates
from app.services.external_database_matchers import match_retailer_receipt_line as _base_match_retailer_receipt_line
from app.services.external_product_index_store import ensure_learned_external_product_candidate
from app.services.product_evidence_packet import apply_product_evidence_to_candidates, build_product_evidence_packet_dict


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

    enriched = dict(result)
    enriched["candidates"] = normalized[:5]
    enriched["uses_product_evidence_scoring"] = True
    enriched["uses_candidate_deduplication"] = len(normalized) < len(rescored)
    enriched["candidate_count_before_deduplication"] = len(rescored)
    enriched["candidate_count_after_deduplication"] = len(normalized[:5])
    enriched["creates_global_product"] = False
    enriched["creates_household_article"] = False
    enriched["creates_inventory_event"] = False
    return enriched


def _match_with_self_learning(retailer_code: str, receipt_line_text: str, include_below_threshold: bool = True) -> dict[str, Any]:
    result = _base_match_retailer_receipt_line(
        retailer_code=retailer_code,
        receipt_line_text=receipt_line_text,
        include_below_threshold=include_below_threshold,
    )
    if result.get("candidates"):
        result["uses_self_learning_external_index"] = False
        return result

    learned = ensure_learned_external_product_candidate(
        receipt_line_text=receipt_line_text,
        retailer_code=retailer_code,
    )
    learned_result = _base_match_retailer_receipt_line(
        retailer_code=retailer_code,
        receipt_line_text=receipt_line_text,
        include_below_threshold=True,
    )
    enriched = dict(learned_result)
    enriched["uses_self_learning_external_index"] = bool(learned.get("ok"))
    enriched["self_learning_external_index"] = {
        "learned": bool(learned.get("learned")),
        "reason": learned.get("reason"),
        "source_name": (learned.get("item") or {}).get("source_name"),
        "source_product_code": (learned.get("item") or {}).get("source_product_code"),
    }
    enriched["creates_global_product"] = False
    enriched["creates_household_article"] = False
    enriched["creates_inventory_event"] = False
    return enriched


def match_retailer_receipt_line(retailer_code: str, receipt_line_text: str, include_below_threshold: bool = True) -> dict[str, Any]:
    result = _match_with_self_learning(
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
