from __future__ import annotations

import sys
from functools import wraps
from typing import Any, Callable

from sqlalchemy import text

from app.db import engine
from app.services import external_product_candidate_store as candidate_store
from app.services.external_product_candidate_store import list_external_receipt_items as _base_list_external_receipt_items


def _text(value: Any) -> str:
    return str(value or "").strip()


def _code(candidate: dict[str, Any]) -> str:
    return (
        _text(candidate.get("retailer_article_number"))
        or _text(candidate.get("candidate_source_product_code"))
        or _text(candidate.get("source_product_code"))
    )


def _candidate_identity(candidate: dict[str, Any]) -> str:
    code = _code(candidate)
    if code:
        return f"code:{code.lower()}"
    return "name:{}:{}".format(
        _text(candidate.get("candidate_source_name") or candidate.get("source_name")).lower(),
        _text(candidate.get("candidate_name")).lower(),
    )


def _candidate_priority(candidate: dict[str, Any]) -> tuple:
    source_priority = {
        "lidl_catalog_enrichment": 5,
        "lidl_product_group": 4,
        "product_taxonomy_seed": 3,
        "OFF-index": 2,
    }
    source = _text(candidate.get("candidate_source_name") or candidate.get("source_name"))
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
    next_item["candidate_source_name"] = _text(best.get("candidate_source_name") or best.get("source_name"))
    next_item["source_name"] = next_item["candidate_source_name"]
    if not _text(next_item.get("quantity_label")):
        next_item["quantity_label"] = _text(best.get("quantity_label")) or None
    if not _text(next_item.get("candidate_brand")):
        next_item["candidate_brand"] = _text(best.get("candidate_brand")) or None
    if next_item.get("candidate_status") == "candidate":
        next_item["is_linkable_to_catalog"] = bool(best_code)
    return next_item


def _table_exists(conn, table_name: str) -> bool:
    dialect_name = str(engine.dialect.name or "").lower()
    if dialect_name == "sqlite":
        return conn.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
            {"table_name": table_name},
        ).first() is not None

    return conn.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = :table_name
            LIMIT 1
            """
        ),
        {"table_name": table_name},
    ).first() is not None


def _candidate_context_keys(rows: list[dict[str, Any]]) -> set[str]:
    return {_text(row.get("context_key")) for row in rows if _text(row.get("context_key"))}


def _receipt_key(row: dict[str, Any]) -> str:
    if hasattr(candidate_store, "_m2c2i_fix7a3_normalized_receipt_key"):
        return candidate_store._m2c2i_fix7a3_normalized_receipt_key(
            row.get("retailer_code"),
            row.get("receipt_line_text"),
        )

    retailer = _text(row.get("retailer_code")).lower()
    receipt_text = _text(row.get("receipt_line_text")).lower().replace(".", "")
    receipt_text = " ".join(receipt_text.split())
    return f"{retailer}|{receipt_text}"


def _receipt_table_line_placeholder(row: dict[str, Any]) -> dict[str, Any]:
    receipt_line_id = _text(row.get("receipt_line_id"))
    retailer_code = _text(row.get("retailer_code")).lower() or "onbekend"
    receipt_line_text = _text(row.get("receipt_line_text"))
    context_key = candidate_store.build_candidate_context_key(
        retailer_code,
        receipt_line_text,
        receipt_line_id=receipt_line_id or None,
    )

    receipt_item_id = f"receipt-table-line:{receipt_line_id}" if receipt_line_id else ""
    return {
        "id": receipt_item_id,
        "receipt_item_id": receipt_item_id,
        "receipt_item_type": "receipt_table_line",
        "receipt_item_source_id": receipt_line_id or None,
        "receipt_line_id": receipt_line_id or None,
        "purchase_import_line_id": None,
        "context_key": context_key,
        "retailer_code": retailer_code,
        "receipt_line_text": receipt_line_text,
        "candidate_name": "",
        "candidate_brand": "",
        "candidate_source_name": "",
        "candidate_source_product_code": "",
        "source_name": "",
        "source_product_code": "",
        "retailer_article_number": _text(row.get("retailer_article_number")) or None,
        "gtin": _text(row.get("retailer_article_number")) or None,
        "quantity_label": _text(row.get("quantity_label")) or None,
        "variant": "",
        "source_url": "",
        "price": row.get("price"),
        "score": 0,
        "score_breakdown_json": "{}",
        "candidate_status": "no_candidate",
        "global_product_id": None,
        "status": "no_candidate",
        "is_probable": 0,
        "is_user_confirmed": 0,
        "is_external_database_override": 0,
        "is_receipt_item_placeholder": True,
        "created_by": "receipt_table_lines",
        "created_at": _text(row.get("created_at")),
        "updated_at": _text(row.get("updated_at")),
    }


def _list_receipt_table_line_placeholders(existing_item_context_keys: set[str], limit: int) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        if not _table_exists(conn, "receipt_table_lines") or not _table_exists(conn, "receipt_tables"):
            return []
        rows = conn.execute(
            text(
                """
                SELECT
                    rtl.id AS receipt_line_id,
                    rt.store_name AS retailer_code,
                    COALESCE(NULLIF(rtl.raw_label, ''), rtl.normalized_label) AS receipt_line_text,
                    rtl.barcode AS retailer_article_number,
                    TRIM(COALESCE(CAST(rtl.quantity AS TEXT), '') || ' ' || COALESCE(CAST(rtl.unit AS TEXT), '')) AS quantity_label,
                    rtl.line_total AS price,
                    rt.created_at AS created_at,
                    rt.updated_at AS updated_at
                FROM receipt_table_lines rtl
                JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
                ORDER BY rt.created_at DESC, rtl.line_index ASC, rtl.id ASC
                LIMIT :limit
                """
            ),
            {"limit": max(1, min(int(limit or 500), 500))},
        ).mappings().all()

    placeholders: list[dict[str, Any]] = []
    for row in rows:
        item = _receipt_table_line_placeholder(dict(row))
        if not item.get("receipt_line_text"):
            continue
        if _text(item.get("context_key")) in existing_item_context_keys:
            continue
        placeholders.append(item)
    return placeholders


def _latest_candidates(limit: int) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT *
                FROM external_product_candidates
                ORDER BY updated_at DESC, score DESC
                LIMIT :limit
                """
            ),
            {"limit": max(1, min(int(limit or 500), 500))},
        ).mappings().all()
    return [dict(row) for row in rows]


def _candidates_by_receipt_key(placeholders: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for placeholder in placeholders:
        key = _receipt_key(placeholder)
        if not key or key == "|":
            continue
        candidates = [dict(candidate) for candidate in list(placeholder.get("candidates") or []) if isinstance(candidate, dict)]
        if not candidates:
            continue
        grouped.setdefault(key, []).extend(candidates)
    return grouped


def _merge_candidates_preserving_visible_item(
    item: dict[str, Any],
    extra_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Vul alleen kandidaatdetails aan; vervang de zichtbare bonartikelrij niet.

    Bestaande artikelcodes/catalogusstatussen van purchase_import_lines blijven leidend.
    Receipt-table-line-kandidaten zijn detailvoorstellen onder dezelfde bonartikeltekst.
    """
    if not extra_candidates:
        return item

    next_item = dict(item)
    original_values = {
        "retailer_article_number": next_item.get("retailer_article_number"),
        "candidate_source_product_code": next_item.get("candidate_source_product_code"),
        "source_product_code": next_item.get("source_product_code"),
        "gtin": next_item.get("gtin"),
        "global_product_id": next_item.get("global_product_id"),
        "status": next_item.get("status"),
        "candidate_status": next_item.get("candidate_status"),
        "is_linked_to_catalog": next_item.get("is_linked_to_catalog"),
        "is_existing_link_for_receipt_item": next_item.get("is_existing_link_for_receipt_item"),
        "canonical_catalog_product_id": next_item.get("canonical_catalog_product_id"),
    }

    merged_candidates = _dedupe_detail_candidates(
        [dict(candidate) for candidate in list(next_item.get("candidates") or []) if isinstance(candidate, dict)]
        + [dict(candidate) for candidate in extra_candidates if isinstance(candidate, dict)]
    )
    next_item["candidates"] = merged_candidates
    next_item["candidate_count"] = len(merged_candidates)
    next_item["has_receipt_table_line_candidate_details"] = bool(merged_candidates)

    status = _text(next_item.get("status") or next_item.get("candidate_status")).lower()
    if merged_candidates and status in {"", "no_candidate"}:
        next_item["status"] = "candidate"
        next_item["candidate_status"] = "candidate"

    # Zet originele zichtbare artikelcodes en cataloguskoppelingen terug zodra die al bestonden.
    # Daarmee kan de nieuwe receipt_table_lines-projectie niets goeds uit de oude weergave wissen.
    for field_name, value in original_values.items():
        if _text(value):
            next_item[field_name] = value

    return next_item


def _merge_receipt_table_candidates_into_existing_items(
    items: list[dict[str, Any]],
    receipt_placeholders: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    candidates_by_key = _candidates_by_receipt_key(receipt_placeholders)
    if not candidates_by_key:
        return items, 0

    merged_count = 0
    merged_items: list[dict[str, Any]] = []
    for item in items:
        key = _receipt_key(item)
        extra_candidates = candidates_by_key.get(key, [])
        if extra_candidates:
            merged_count += 1
            merged_items.append(_merge_candidates_preserving_visible_item(item, extra_candidates))
        else:
            merged_items.append(item)

    return merged_items, merged_count


def _append_missing_receipt_table_placeholders(
    items: list[dict[str, Any]],
    receipt_placeholders: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    visible_keys = {_receipt_key(item) for item in items if _receipt_key(item)}
    missing = [
        placeholder
        for placeholder in receipt_placeholders
        if _receipt_key(placeholder) and _receipt_key(placeholder) not in visible_keys
    ]
    if not missing:
        return items, 0
    return items + missing, len(missing)


def _enrich_receipt_table_items(result: dict[str, Any], limit: int) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit or 500), 500))
    items = [dict(item) for item in list(result.get("items") or []) if isinstance(item, dict)]
    existing_item_context_keys = _candidate_context_keys(items)
    candidates = _latest_candidates(normalized_limit)
    receipt_placeholders = _list_receipt_table_line_placeholders(existing_item_context_keys, normalized_limit)

    if hasattr(candidate_store, "_m2c2i_fix7a3_apply_catalog_status_to_placeholders"):
        receipt_placeholders = candidate_store._m2c2i_fix7a3_apply_catalog_status_to_placeholders(
            receipt_placeholders,
            candidates,
        )

    items_with_merged_candidates, merged_existing_rows = _merge_receipt_table_candidates_into_existing_items(
        items,
        receipt_placeholders,
    )
    combined, appended_receipt_table_rows = _append_missing_receipt_table_placeholders(
        items_with_merged_candidates,
        receipt_placeholders,
    )

    combined = [_project_best_candidate(item) for item in combined]
    if hasattr(candidate_store, "_m2c2i_fix2_apply_status_fields"):
        combined = candidate_store._m2c2i_fix2_apply_status_fields(combined)
    if hasattr(candidate_store, "_m2c2i_fix7b_dedupe_top_receipt_items"):
        combined = candidate_store._m2c2i_fix7b_dedupe_top_receipt_items(combined)

    next_result = dict(result)
    next_result["items"] = combined[:normalized_limit]
    next_result["receipt_table_line_rows"] = len(receipt_placeholders)
    next_result["receipt_table_candidate_merge_rows"] = merged_existing_rows
    next_result["receipt_table_placeholder_append_rows"] = appended_receipt_table_rows
    next_result["total"] = len(next_result["items"])
    next_result["uses_candidate_projection_normalization"] = True
    next_result["uses_receipt_table_line_projection"] = True
    next_result["receipt_table_lines_are_supplemental"] = True
    next_result["creates_global_product"] = False
    next_result["creates_household_article"] = False
    next_result["creates_inventory_event"] = False
    return next_result


def list_external_receipt_items(limit: int = 500) -> dict[str, Any]:
    result = _base_list_external_receipt_items(limit=limit)
    return _enrich_receipt_table_items(result, limit)


def _wrap_list_external_receipt_items(original: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(original)
    def wrapped(limit: int = 500) -> dict[str, Any]:
        result = original(limit=limit)
        if not isinstance(result, dict):
            return result
        return _enrich_receipt_table_items(result, limit)

    return wrapped


def _patch_module_function(module: Any, function_name: str, wrapper_factory: Callable[[Callable[..., Any]], Callable[..., Any]]) -> bool:
    original = getattr(module, function_name, None)
    if not callable(original):
        return False
    marker_name = f"_m2c2i24sa_original_{function_name}"
    if hasattr(module, marker_name):
        return False
    setattr(module, marker_name, original)
    setattr(module, function_name, wrapper_factory(original))
    return True


def install_receipt_table_line_projection() -> dict[str, Any]:
    patched: list[str] = []
    if _patch_module_function(candidate_store, "list_external_receipt_items", _wrap_list_external_receipt_items):
        patched.append("app.services.external_product_candidate_store.list_external_receipt_items")

    system_routes = sys.modules.get("app.api.system_routes")
    if system_routes is not None:
        if _patch_module_function(system_routes, "list_external_receipt_items", _wrap_list_external_receipt_items):
            patched.append("app.api.system_routes.list_external_receipt_items")

    return {
        "ok": True,
        "patched": patched,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
