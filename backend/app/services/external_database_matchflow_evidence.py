from __future__ import annotations

from typing import Any

from app.services import external_product_candidate_store as candidate_store
from app.services.external_candidate_normalization import normalize_external_candidates
from app.services.external_database_matchers import match_retailer_receipt_line as _base_match_retailer_receipt_line
from app.services.external_product_index_store import ensure_learned_external_product_candidate
from app.services.product_evidence_packet import apply_product_evidence_to_candidates, build_product_evidence_packet_dict

MIN_USEFUL_CANDIDATE_SCORE = 0.70
NON_USEFUL_SOURCES = {
    "receipt_unresolved_fallback",
    "receipt_product_intent_fallback",
}


def _candidate_source(candidate: dict[str, Any]) -> str:
    return str(candidate.get("candidate_source_name") or candidate.get("source_name") or "").strip()


def _is_useful_candidate(candidate: dict[str, Any]) -> bool:
    source_name = _candidate_source(candidate)
    if source_name in NON_USEFUL_SOURCES:
        return False
    if source_name == "learned_receipt_line":
        return True
    status = str(candidate.get("candidate_status") or candidate.get("status") or "").strip().lower()
    if status in {"probable_candidate", "user_confirmed", "external_database_override", "linked_to_catalog"}:
        return True
    return float(candidate.get("score") or 0.0) >= MIN_USEFUL_CANDIDATE_SCORE


def _has_useful_candidate(candidates: list[dict[str, Any]]) -> bool:
    return any(_is_useful_candidate(candidate) for candidate in candidates)


def _append_learned_candidate(result: dict[str, Any], learned: dict[str, Any]) -> dict[str, Any]:
    item = learned.get("item") or {}
    if not item:
        return result

    candidate = {
        "candidate_name": item.get("product_name") or result.get("receipt_line_text") or "Onbekend bonartikel",
        "candidate_brand": item.get("brand") or result.get("retailer_code") or "",
        "candidate_source_name": item.get("source_name") or "learned_receipt_line",
        "candidate_source_product_code": item.get("source_product_code") or item.get("code") or "",
        "source_name": item.get("source_name") or "learned_receipt_line",
        "source_product_code": item.get("source_product_code") or item.get("code") or "",
        "retailer_article_number": item.get("source_product_code") or item.get("code") or "",
        "quantity_label": item.get("quantity") or item.get("net_content") or "",
        "variant": "",
        "source_url": item.get("source_url") or "",
        "score": 0.71,
        "score_breakdown": {"self_learning_concept_candidate": True},
        "candidate_status": "concept_candidate",
        "is_probable": False,
        "is_user_confirmed": False,
        "is_external_database_override": False,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "created_by": "m2c2i20r_self_learning_candidate",
    }

    enriched = dict(result)
    existing_candidates = list(enriched.get("candidates") or [])
    source_code = str(candidate.get("candidate_source_product_code") or "").strip()
    if source_code and not any(
        str(existing.get("candidate_source_product_code") or existing.get("source_product_code") or existing.get("retailer_article_number") or "").strip() == source_code
        for existing in existing_candidates
    ):
        existing_candidates.append(candidate)
    enriched["candidates"] = existing_candidates
    return enriched


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
    initial_candidates = list(result.get("candidates") or [])
    if _has_useful_candidate(initial_candidates):
        result["uses_self_learning_external_index"] = False
        result["self_learning_reason"] = "useful_candidate_already_available"
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
    enriched = _append_learned_candidate(dict(learned_result), learned)
    enriched["uses_self_learning_external_index"] = bool(learned.get("ok"))
    enriched["self_learning_external_index"] = {
        "learned": bool(learned.get("learned")),
        "reason": learned.get("reason"),
        "source_name": (learned.get("item") or {}).get("source_name"),
        "source_product_code": (learned.get("item") or {}).get("source_product_code"),
        "trigger": "no_useful_candidate",
        "initial_candidate_count": len(initial_candidates),
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
