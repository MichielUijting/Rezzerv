from __future__ import annotations

import importlib
import logging
import sys
from typing import Any, Callable

from sqlalchemy import text

from app.db import engine
from app.services.external_product_candidate_store import build_candidate_context_key

LOGGER = logging.getLogger(__name__)


def _text(value: Any) -> str:
    return str(value or "").strip()


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


def _receipt_table_line_placeholders(limit: int) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(int(limit or 500), 500))

    with engine.begin() as conn:
        if not _table_exists(conn, "receipt_tables") or not _table_exists(conn, "receipt_table_lines"):
            return []

        rows = conn.execute(
            text(
                """
                SELECT
                    rtl.id AS receipt_line_id,
                    rtl.receipt_table_id AS receipt_table_id,
                    rtl.line_index AS line_index,
                    rt.store_name AS store_name,
                    COALESCE(NULLIF(rtl.raw_label, ''), rtl.normalized_label) AS receipt_line_text,
                    rtl.normalized_label AS normalized_label,
                    rtl.barcode AS barcode,
                    rtl.quantity AS quantity,
                    rtl.unit AS unit,
                    rtl.line_total AS line_total,
                    rt.created_at AS created_at,
                    rt.updated_at AS updated_at
                FROM receipt_table_lines rtl
                JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
                ORDER BY rt.created_at DESC, rtl.line_index ASC, rtl.id ASC
                LIMIT :limit
                """
            ),
            {"limit": normalized_limit},
        ).mappings().all()

    placeholders: list[dict[str, Any]] = []
    for row in rows:
        receipt_line_id = _text(row.get("receipt_line_id"))
        receipt_text = _text(row.get("receipt_line_text")) or _text(row.get("normalized_label"))
        if not receipt_line_id or not receipt_text:
            continue

        retailer_code = _text(row.get("store_name")) or "onbekend"
        quantity_label = " ".join([
            _text(row.get("quantity")),
            _text(row.get("unit")),
        ]).strip() or None
        context_key = build_candidate_context_key(
            retailer_code,
            receipt_text,
            receipt_line_id=receipt_line_id,
        )

        placeholders.append({
            "id": f"{context_key}:receipt-item",
            "receipt_line_id": receipt_line_id,
            "purchase_import_line_id": None,
            "context_key": context_key,
            "retailer_code": retailer_code,
            "receipt_line_text": receipt_text,
            "candidate_name": "",
            "candidate_brand": "",
            "candidate_source_name": "",
            "candidate_source_product_code": "",
            "source_name": "",
            "source_product_code": "",
            "retailer_article_number": _text(row.get("barcode")) or None,
            "gtin": _text(row.get("barcode")) or None,
            "quantity_label": quantity_label,
            "variant": "",
            "source_url": "",
            "price": row.get("line_total"),
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
        })

    return placeholders


def _wrap_list_external_receipt_items(original: Callable[..., dict[str, Any]], store_module: Any) -> Callable[..., dict[str, Any]]:
    def wrapped(limit: int = 500) -> dict[str, Any]:
        result = original(limit=limit)
        normalized_limit = max(1, min(int(limit or 500), 500))
        existing_items = list(result.get("items") or [])
        receipt_placeholders = _receipt_table_line_placeholders(normalized_limit)

        if not receipt_placeholders:
            return result

        with engine.begin() as conn:
            candidate_rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM external_product_candidates
                    ORDER BY updated_at DESC, score DESC
                    LIMIT :limit
                    """
                ),
                {"limit": normalized_limit},
            ).mappings().all()
            candidates = [dict(row) for row in candidate_rows]

        try:
            receipt_placeholders = store_module._m2c2i_fix7a3_apply_catalog_status_to_placeholders(
                receipt_placeholders,
                candidates,
            )
        except Exception as exc:
            LOGGER.warning("Projectie van receipt_table_lines-kandidaten mislukt: %s", exc)

        combined = receipt_placeholders + existing_items
        try:
            combined = store_module._m2c2i_fix7b_dedupe_top_receipt_items(combined)
        except Exception:
            seen: set[str] = set()
            unique: list[dict[str, Any]] = []
            for item in combined:
                key = _text(item.get("context_key")) or _text(item.get("id"))
                if key in seen:
                    continue
                seen.add(key)
                unique.append(item)
            combined = unique

        next_result = dict(result)
        next_result["items"] = combined[:normalized_limit]
        next_result["receipt_table_line_rows"] = len(receipt_placeholders)
        next_result["total"] = len(next_result["items"])
        return next_result

    return wrapped


def install_receipt_table_line_projection() -> dict[str, Any]:
    store_module = importlib.import_module("app.services.external_product_candidate_store")
    original = getattr(store_module, "list_external_receipt_items", None)
    if not callable(original):
        return {"ok": False, "patched": [], "reason": "list_external_receipt_items_missing"}

    patched: list[str] = []
    if not hasattr(store_module, "_m2c2i24sa_original_list_external_receipt_items"):
        setattr(store_module, "_m2c2i24sa_original_list_external_receipt_items", original)
        setattr(
            store_module,
            "list_external_receipt_items",
            _wrap_list_external_receipt_items(original, store_module),
        )
        patched.append("app.services.external_product_candidate_store.list_external_receipt_items")

    system_routes = sys.modules.get("app.api.system_routes")
    if system_routes is not None:
        setattr(system_routes, "list_external_receipt_items", getattr(store_module, "list_external_receipt_items"))
        patched.append("app.api.system_routes.list_external_receipt_items")

    coverage_report = sys.modules.get("app.services.external_receipt_coverage_report")
    if coverage_report is not None:
        setattr(coverage_report, "list_external_receipt_items", getattr(store_module, "list_external_receipt_items"))
        patched.append("app.services.external_receipt_coverage_report.list_external_receipt_items")

    return {
        "ok": True,
        "patched": patched,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
