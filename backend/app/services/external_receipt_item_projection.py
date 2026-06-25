from __future__ import annotations

from typing import Any

from app.services.external_product_candidate_store import list_external_receipt_items as _base_list_external_receipt_items


def _code(candidate: dict[str, Any]) -> str:
    return (
        str(candidate.get("retailer_article_number") or "").strip()
        or str(candidate.get("candidate_source_product_code") or "").strip()
        or str(candidate.get("source_product_code") or "").strip()
    )


def _candidate_identity(candidate: dict[str, Any]) -> str:
    code = _code(candidate)
    if code:
        return f"code:{code.lower()}"
    return "name:{}:{}".format(
        str(candidate.get("candidate_source_name") or candidate.get("source_name") or "").strip().lower(),
        str(candidate.get("candidate_name") or "").strip().lower(),
    )


def _candidate_priority(candidate: dict[str, Any]) -> tuple:
    source_priority = {
        "lidl_catalog_enrichment": 5,
        "lidl_product_group": 4,
        "product_taxonomy_seed": 3,
        "OFF-index": 2,
    }
    source = str(candidate.get("candidate_source_name") or candidate.get("source_name") or "").strip()
    return (
        float(candidate.get("score") or 0.0),
        source_priority.get(source, 1),
        1 if _code(candidate) else 0,
    )


def _dedupe_detail_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_identity: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        identity = _candidate_identity(candidate)
        existing = best_by_identity.get(identity)
        if existing is None or _candidate_priority(candidate) > _candidate_priority(existing):
            best_by_identity[identity] = dict(candidate)
    return sorted(best_by_identity.values(), key=_candidate_priority, reverse=True)


def _project_best_candidate(item: dict[str, Any]) -> dict[str, Any]:
    next_item = dict(item)
    detail_candidates = _dedupe_detail_candidates(list(next_item.get("candidates") or []))
    next_item["candidates"] = detail_candidates
    next_item["candidate_count"] = len(detail_candidates)

    if not detail_candidates:
        return next_item

    best = detail_candidates[0]
    best_code = _code(best)
    if best_code:
        next_item["retailer_article_number"] = best_code
        next_item["candidate_source_product_code"] = best_code
        next_item["source_product_code"] = best_code
    next_item["candidate_source_name"] = str(best.get("candidate_source_name") or best.get("source_name") or "").strip()
    next_item["source_name"] = next_item["candidate_source_name"]
    if not str(next_item.get("quantity_label") or "").strip():
        next_item["quantity_label"] = str(best.get("quantity_label") or "").strip() or None
    if not str(next_item.get("candidate_brand") or "").strip():
        next_item["candidate_brand"] = str(best.get("candidate_brand") or "").strip() or None
    if next_item.get("candidate_status") == "candidate":
        next_item["is_linkable_to_catalog"] = bool(best_code)
    return next_item


def list_external_receipt_items(limit: int = 500) -> dict[str, Any]:
    result = _base_list_external_receipt_items(limit=limit)
    items = [_project_best_candidate(dict(item)) for item in list(result.get("items") or [])]
    next_result = dict(result)
    next_result["items"] = items
    next_result["uses_candidate_projection_normalization"] = True
    next_result["creates_global_product"] = False
    next_result["creates_household_article"] = False
    next_result["creates_inventory_event"] = False
    return next_result
