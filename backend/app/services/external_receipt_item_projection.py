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


def _receipt_table_line_placeholder(row: dict[str, Any]) -> dict[str, Any]:
    receipt_line_id = _text(row.get("receipt_line_id"))
    retailer_code = _text(row.get("retailer_code")).lower() or "onbekend"
    receipt_line_text = _text(row.get("receipt_line_text"))
    context_key = candidate_store.build_candidate_context_key(
        retailer_code,
        receipt_line_text,
        receipt_line_id=receipt_line_id or None,
    )

    return {
        "id": f"{context_key}:receipt-item",
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

    combined = [_project_best_candidate(item) for item in items + receipt_placeholders]
    if hasattr(candidate_store, "_m2c2i_fix2_apply_status_fields"):
        combined = candidate_store._m2c2i_fix2_apply_status_fields(combined)
    if hasattr(candidate_store, "_m2c2i_fix7b_dedupe_top_receipt_items"):
        combined = candidate_store._m2c2i_fix7b_dedupe_top_receipt_items(combined)

    next_result = dict(result)
    next_result["items"] = combined[:normalized_limit]
    next_result["receipt_table_line_rows"] = len(receipt_placeholders)
    next_result["total"] = len(next_result["items"])
    next_result["uses_candidate_projection_normalization"] = True
    next_result["uses_receipt_table_line_projection"] = True
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
