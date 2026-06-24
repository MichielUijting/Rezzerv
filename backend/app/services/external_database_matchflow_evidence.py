from __future__ import annotations

from typing import Any

from app.services import external_product_candidate_store as candidate_store
from app.services.external_database_matchers import match_retailer_receipt_line as _base_match_retailer_receipt_line
from app.services.product_evidence_packet import apply_product_evidence_to_candidates


def _with_evidence_scoring(result: dict[str, Any], receipt_line_text: str, retailer_code: str) -> dict[str, Any]:
    candidates = list(result.get("candidates") or [])
    if not candidates:
        return result

    rescored = apply_product_evidence_to_candidates(
        receipt_line_text,
        retailer_code,
        candidates,
    )
    enriched = dict(result)
    enriched["candidates"] = rescored[: len(candidates)]
    enriched["uses_product_evidence_scoring"] = True
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
