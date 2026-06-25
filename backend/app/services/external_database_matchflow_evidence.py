from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services import external_product_candidate_store as candidate_store
from app.services.external_candidate_normalization import normalize_external_candidates
from app.services.external_database_matchers import match_retailer_receipt_line as _base_match_retailer_receipt_line
from app.services.external_product_alias_store import find_alias_candidates, save_alias_from_candidate
from app.services.lidl_local_catalog_index import search_lidl_local_catalog_candidates
from app.services.product_evidence_packet import apply_product_evidence_to_candidates, build_product_evidence_packet_dict


M2C2I20_RESOLVED_EXTERNAL_STATUSES = {
    "resolved",
    "external_resolved",
    "linked_to_catalog",
    "user_confirmed",
}

M2C2I20_EXTERNAL_CODE_FIELDS = (
    "external_product_code",
    "external_source_product_code",
    "external_product_index_id",
    "external_article_code",
    "retailer_article_number",
    "gtin",
    "ean",
)

_M2C2I20A_PERFORMANCE_INDEXES_READY = False


def _m2c2i21_catalog_candidates(retailer_code: str, receipt_line_text: str) -> list[dict[str, Any]]:
    if str(retailer_code or "").strip().lower() != "lidl":
        return []
    return search_lidl_local_catalog_candidates(receipt_line_text, limit=5)


def _with_evidence_scoring(result: dict[str, Any], receipt_line_text: str, retailer_code: str) -> dict[str, Any]:
    base_candidates = list(result.get("candidates") or [])
    alias_candidates = find_alias_candidates(retailer_code, receipt_line_text)
    catalog_candidates = _m2c2i21_catalog_candidates(retailer_code, receipt_line_text)
    candidates = alias_candidates + catalog_candidates + base_candidates
    if not candidates:
        enriched_empty = dict(result)
        enriched_empty["uses_product_evidence_scoring"] = True
        enriched_empty["uses_candidate_deduplication"] = False
        enriched_empty["uses_retailer_alias_learning"] = bool(alias_candidates)
        enriched_empty["uses_lidl_local_catalog_index"] = bool(catalog_candidates)
        enriched_empty["lidl_local_catalog_candidate_count"] = len(catalog_candidates)
        enriched_empty["candidate_count_before_deduplication"] = 0
        enriched_empty["candidate_count_after_deduplication"] = 0
        enriched_empty["creates_global_product"] = False
        enriched_empty["creates_household_article"] = False
        enriched_empty["creates_inventory_event"] = False
        return enriched_empty

    evidence_packet = build_product_evidence_packet_dict(receipt_line_text, retailer_code=retailer_code)
    rescored = apply_product_evidence_to_candidates(
        receipt_line_text,
        retailer_code,
        candidates,
        evidence_packet=evidence_packet,
    )
    normalized = normalize_external_candidates(rescored, evidence_packet=evidence_packet)

    if normalized:
        save_alias_from_candidate(
            retailer_code=retailer_code,
            receipt_line_text=receipt_line_text,
            candidate=normalized[0],
            learned_from="matchflow_evidence",
        )

    enriched = dict(result)
    enriched["candidates"] = normalized[:5]
    enriched["uses_product_evidence_scoring"] = True
    enriched["uses_candidate_deduplication"] = len(normalized) < len(rescored)
    enriched["uses_retailer_alias_learning"] = bool(alias_candidates)
    enriched["uses_lidl_local_catalog_index"] = bool(catalog_candidates)
    enriched["lidl_local_catalog_candidate_count"] = len(catalog_candidates)
    enriched["candidate_count_before_deduplication"] = len(rescored)
    enriched["candidate_count_after_deduplication"] = len(normalized[:5])
    enriched["alias_candidate_count"] = len(alias_candidates)
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


def _m2c2i20_truthy(value: Any) -> bool:
    normalized = str(value if value is not None else "").strip().lower()
    return bool(normalized and normalized not in {"-", "0", "none", "null", "undefined", "false", "unknown", "onbekend"})


def m2c2i20_external_product_code(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    for field_name in M2C2I20_EXTERNAL_CODE_FIELDS:
        value = str(item.get(field_name) if item.get(field_name) is not None else "").strip()
        if _m2c2i20_truthy(value):
            return value
    return ""


def is_m2c2i20_external_resolved_item(item: dict[str, Any] | None) -> bool:
    """Return True when a receipt item already has a usable external article code.

    M2C2i-20 rule: a receipt item that already has an external product code is resolved
    for the external-database flow and must not be searched again.
    """
    if not isinstance(item, dict):
        return False

    external_code = m2c2i20_external_product_code(item)
    if not external_code:
        return False

    status_values = {
        str(item.get("external_match_status") or "").strip().lower(),
        str(item.get("status") or "").strip().lower(),
        str(item.get("candidate_status") or "").strip().lower(),
    }
    if status_values & M2C2I20_RESOLVED_EXTERNAL_STATUSES:
        return True

    if bool(item.get("is_external_resolved")) or bool(item.get("is_linked_to_catalog")):
        return True

    # Bovenste tabelrijen zijn bonartikelgedreven. Als zo'n rij al een externe code
    # heeft, dan is zoeken op bontekst niet meer nodig.
    if bool(item.get("is_receipt_item_placeholder")):
        return True
    if _m2c2i20_truthy(item.get("purchase_import_line_id")) or _m2c2i20_truthy(item.get("receipt_line_id")):
        return True

    return False


def _m2c2i20_resolved_skip_entry(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "reason": "external_product_code_resolved",
        "receipt_line_text": str(item.get("receipt_line_text") or item.get("receiptLineText") or "").strip(),
        "retailer_code": str(item.get("retailer_code") or item.get("retailerCode") or "").strip().lower(),
        "receipt_line_id": str(item.get("receipt_line_id") or item.get("receiptLineId") or "").strip() or None,
        "purchase_import_line_id": str(item.get("purchase_import_line_id") or item.get("purchaseImportLineId") or "").strip() or None,
        "external_product_code": m2c2i20_external_product_code(item),
    }


def _m2c2i20_split_resolved_items(items: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    unresolved: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    for item in items or []:
        next_item = dict(item) if isinstance(item, dict) else item
        if is_m2c2i20_external_resolved_item(next_item):
            resolved.append(next_item)
        else:
            unresolved.append(next_item)
    return unresolved, resolved


def _m2c2i20a_ensure_performance_indexes() -> None:
    """Maak lichte indexen voor de Externe databases paging/refresh-flow.

    De UI werkt bonartikelgedreven. Bij paginawissels en refreshes filteren we vooral op
    context_key, purchase_import_line_id en receipt_line_id. Zonder indexen groeit de
    reactietijd merkbaar zodra external_product_candidates meer historie bevat.
    """
    global _M2C2I20A_PERFORMANCE_INDEXES_READY
    if _M2C2I20A_PERFORMANCE_INDEXES_READY:
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_m2c2i20a_candidates_context_updated
                ON external_product_candidates (context_key, updated_at)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_m2c2i20a_candidates_purchase_line
                ON external_product_candidates (purchase_import_line_id, updated_at)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_m2c2i20a_candidates_receipt_line
                ON external_product_candidates (receipt_line_id, updated_at)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_m2c2i20a_candidates_status_context
                ON external_product_candidates (candidate_status, status, context_key)
                """
            )
        )

    _M2C2I20A_PERFORMANCE_INDEXES_READY = True


def _m2c2i20_call_candidate_store_ensure(args: tuple[Any, ...], kwargs: dict[str, Any], unresolved_items: list[dict[str, Any]]) -> dict[str, Any]:
    next_kwargs = dict(kwargs)
    if "items" in next_kwargs:
        next_kwargs["items"] = unresolved_items
        return candidate_store.ensure_external_receipt_item_candidates(*args, **next_kwargs)
    return candidate_store.ensure_external_receipt_item_candidates(unresolved_items, *args[1:], **next_kwargs)


def _m2c2i20_enrich_ensure_result(result: dict[str, Any], original_total: int, resolved_items: list[dict[str, Any]]) -> dict[str, Any]:
    enriched = dict(result or {})
    resolved_skips = [_m2c2i20_resolved_skip_entry(item) for item in resolved_items]
    enriched["total"] = original_total
    enriched["skipped_count"] = int(enriched.get("skipped_count") or 0) + len(resolved_skips)
    enriched["external_resolved_skipped_count"] = len(resolved_skips)
    enriched["external_resolved_skipped"] = resolved_skips
    enriched["m2c2i20_resolved_state_gate"] = True
    enriched["m2c2i20a_performance_indexes"] = True
    enriched["creates_global_product"] = False
    enriched["creates_household_article"] = False
    enriched["creates_inventory_event"] = False
    return enriched


def save_matchpreview_candidates(*args: Any, **kwargs: Any) -> dict[str, Any]:
    previous_matcher = candidate_store.match_retailer_receipt_line
    candidate_store.match_retailer_receipt_line = match_retailer_receipt_line
    try:
        return candidate_store.save_matchpreview_candidates(*args, **kwargs)
    finally:
        candidate_store.match_retailer_receipt_line = previous_matcher


def ensure_external_receipt_item_candidates(*args: Any, **kwargs: Any) -> dict[str, Any]:
    _m2c2i20a_ensure_performance_indexes()

    items = kwargs.get("items") if "items" in kwargs else (args[0] if args else None)
    if items is not None:
        normalized_items = [dict(item) for item in (items or []) if isinstance(item, dict)]
        unresolved_items, resolved_items = _m2c2i20_split_resolved_items(normalized_items)
    else:
        normalized_items = []
        unresolved_items = []
        resolved_items = []

    previous_matcher = candidate_store.match_retailer_receipt_line
    candidate_store.match_retailer_receipt_line = match_retailer_receipt_line
    try:
        if items is None:
            return candidate_store.ensure_external_receipt_item_candidates(*args, **kwargs)
        if not unresolved_items:
            return _m2c2i20_enrich_ensure_result(
                {
                    "ok": True,
                    "processed": 0,
                    "saved_count": 0,
                    "updated_count": 0,
                    "skipped_count": 0,
                    "errors": [],
                },
                len(normalized_items),
                resolved_items,
            )
        result = _m2c2i20_call_candidate_store_ensure(args, kwargs, unresolved_items)
        return _m2c2i20_enrich_ensure_result(result, len(normalized_items), resolved_items)
    finally:
        candidate_store.match_retailer_receipt_line = previous_matcher
