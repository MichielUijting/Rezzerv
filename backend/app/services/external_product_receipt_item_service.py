from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_product_candidate_store import (
    build_candidate_context_key,
    ensure_external_product_candidates_schema,
    save_matchpreview_candidates,
)

LINKED_STATUSES = {"linked_to_catalog", "user_confirmed", "external_database_override"}
FALSEY_TEXT_VALUES = {"", "-", "0", "none", "null", "undefined", "false"}


def _truthy(value: Any) -> bool:
    normalized = str(value if value is not None else "").strip().lower()
    return normalized not in FALSEY_TEXT_VALUES


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


def _table_columns(conn, table_name: str) -> set[str]:
    dialect_name = str(engine.dialect.name or "").lower()
    if dialect_name == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        return {str(row.get("name") or "") for row in rows}

    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).mappings().all()
    return {str(row.get("column_name") or "") for row in rows}


def _column_expr(alias: str, columns: set[str], names: list[str], fallback: str = "''") -> str:
    for name in names:
        if name in columns:
            return f"{alias}.{name}"
    return fallback


def _context_key(row: dict[str, Any]) -> str:
    return str(
        row.get("context_key")
        or row.get("receipt_line_id")
        or row.get("purchase_import_line_id")
        or row.get("receipt_line_text")
        or ""
    ).strip()


def _has_catalog_reference(row: dict[str, Any]) -> bool:
    return any(
        _truthy(row.get(field))
        for field in (
            "global_product_id",
            "product_identity_id",
            "matched_global_product_id",
            "matched_global_article_id",
        )
    )


def _has_external_candidate_identity(row: dict[str, Any]) -> bool:
    return bool(
        _truthy(row.get("candidate_name"))
        and (_truthy(row.get("candidate_source_name")) or _truthy(row.get("source_name")))
        and (
            _truthy(row.get("candidate_source_product_code"))
            or _truthy(row.get("source_product_code"))
            or _truthy(row.get("retailer_article_number"))
        )
    )


def _is_placeholder(row: dict[str, Any]) -> bool:
    return bool(row.get("is_receipt_item_placeholder"))


def _has_link_status(row: dict[str, Any]) -> bool:
    status_values = {
        str(row.get("candidate_status") or "").strip().lower(),
        str(row.get("status") or "").strip().lower(),
    }
    return bool(
        LINKED_STATUSES & status_values
        or bool(row.get("is_user_confirmed"))
        or bool(row.get("is_external_database_override"))
    )


def _link_priority(row: dict[str, Any], index: int) -> tuple[int, int, int, int]:
    status = str(row.get("candidate_status") or row.get("status") or "").strip().lower()
    return (
        0 if bool(row.get("is_user_confirmed")) else 1,
        0 if bool(row.get("is_external_database_override")) else 1,
        0 if status == "linked_to_catalog" else 1,
        index,
    )


def _status_label(row: dict[str, Any]) -> str:
    if bool(row.get("is_linked_to_catalog")):
        return "Gekoppeld"
    if bool(row.get("is_linkable_to_catalog")):
        status = str(row.get("candidate_status") or row.get("status") or "").strip().lower()
        if status == "weak_candidate":
            return "Lage zekerheid"
        if status == "probable_candidate":
            return "Waarschijnlijke kandidaat"
        return "Kandidaat"
    if _is_placeholder(row):
        return "Geen kandidaat"
    status = str(row.get("candidate_status") or row.get("status") or "").strip().lower()
    if status == "weak_candidate":
        return "Lage zekerheid"
    if status == "probable_candidate":
        return "Waarschijnlijke kandidaat"
    return "Kandidaat"


def _apply_status_contract(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(_context_key(row), []).append((index, row))

    active_link_indices: set[int] = set()
    group_has_active_link: dict[str, bool] = {}

    for context_key, entries in groups.items():
        linked_entries = [
            (index, row)
            for index, row in entries
            if not _is_placeholder(row) and _has_link_status(row)
        ]
        if linked_entries:
            linked_entries.sort(key=lambda item: _link_priority(item[1], item[0]))
            active_link_indices.add(linked_entries[0][0])
            group_has_active_link[context_key] = True
        else:
            group_has_active_link[context_key] = False

    enriched: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        next_row = dict(row)
        context_key = _context_key(next_row)
        is_linked = index in active_link_indices
        is_linkable = bool(
            not _is_placeholder(next_row)
            and not is_linked
            and (
                group_has_active_link.get(context_key, False)
                or _has_catalog_reference(next_row)
                or _has_external_candidate_identity(next_row)
            )
        )

        next_row["is_linked_to_catalog"] = is_linked
        next_row["is_existing_link_for_receipt_item"] = is_linked
        next_row["is_linkable_to_catalog"] = is_linkable

        if is_linked:
            next_row["candidate_status"] = "linked_to_catalog"
            next_row["status"] = "linked_to_catalog"
        elif str(next_row.get("candidate_status") or "").strip().lower() in LINKED_STATUSES:
            next_row["candidate_status"] = "candidate"
            next_row["status"] = "candidate"

        next_row["status_label"] = _status_label(next_row)
        enriched.append(next_row)

    return enriched


def _candidate_context_keys(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("context_key") or "").strip() for row in rows if str(row.get("context_key") or "").strip()}


def _purchase_import_placeholder(row: dict[str, Any]) -> dict[str, Any]:
    purchase_import_line_id = str(row.get("purchase_import_line_id") or "").strip()
    article_name = str(row.get("article_name_raw") or "").strip()
    context_key = build_candidate_context_key(
        "import",
        article_name or purchase_import_line_id,
        purchase_import_line_id=purchase_import_line_id or None,
    )
    global_product_id = str(row.get("global_product_id") or "").strip()

    return {
        "id": f"{context_key}:receipt-item",
        "receipt_line_id": None,
        "purchase_import_line_id": purchase_import_line_id or None,
        "context_key": context_key,
        "retailer_code": str(row.get("retailer_code") or "import").strip().lower() or "import",
        "receipt_line_text": article_name or str(row.get("external_article_code") or "").strip(),
        "candidate_name": "",
        "candidate_brand": str(row.get("brand_raw") or "").strip(),
        "candidate_source_name": "",
        "candidate_source_product_code": "",
        "source_name": "",
        "source_product_code": "",
        "retailer_article_number": str(row.get("external_article_code") or "").strip() or None,
        "gtin": str(row.get("external_article_code") or "").strip() or None,
        "quantity_label": " ".join([
            str(row.get("quantity_raw") or "").strip(),
            str(row.get("unit_raw") or "").strip(),
        ]).strip() or None,
        "variant": "",
        "source_url": "",
        "price": row.get("line_price_raw"),
        "score": 0,
        "score_breakdown_json": "{}",
        "candidate_status": "no_candidate",
        "global_product_id": global_product_id or None,
        "status": "linked_to_catalog" if global_product_id else "no_candidate",
        "is_probable": 0,
        "is_user_confirmed": 0,
        "is_external_database_override": 0,
        "is_receipt_item_placeholder": True,
        "created_by": "purchase_import_lines",
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _list_purchase_import_placeholders(conn, existing_context_keys: set[str], limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "purchase_import_lines"):
        return []

    columns = _table_columns(conn, "purchase_import_lines")
    id_expr = _column_expr("pil", columns, ["id"])
    code_expr = _column_expr("pil", columns, ["external_article_code"])
    name_expr = _column_expr("pil", columns, ["article_name_raw"])
    brand_expr = _column_expr("pil", columns, ["brand_raw"])
    quantity_expr = _column_expr("pil", columns, ["quantity_raw"])
    unit_expr = _column_expr("pil", columns, ["unit_raw"])
    price_expr = _column_expr("pil", columns, ["line_price_raw"])
    product_expr = _column_expr("pil", columns, ["matched_global_product_id", "matched_global_article_id"])
    created_expr = _column_expr("pil", columns, ["created_at"])
    updated_expr = _column_expr("pil", columns, ["updated_at"])
    order_expr = "pil.ui_sort_order ASC, pil.created_at DESC, pil.id DESC" if "ui_sort_order" in columns else "pil.id DESC"

    rows = conn.execute(
        text(
            f"""
            SELECT
                {id_expr} AS purchase_import_line_id,
                {code_expr} AS external_article_code,
                {name_expr} AS article_name_raw,
                {brand_expr} AS brand_raw,
                {quantity_expr} AS quantity_raw,
                {unit_expr} AS unit_raw,
                {price_expr} AS line_price_raw,
                {product_expr} AS global_product_id,
                {created_expr} AS created_at,
                {updated_expr} AS updated_at
            FROM purchase_import_lines pil
            ORDER BY {order_expr}
            LIMIT :limit
            """
        ),
        {"limit": max(1, min(int(limit or 500), 500))},
    ).mappings().all()

    placeholders = []
    for row in rows:
        item = _purchase_import_placeholder(dict(row))
        if not item.get("receipt_line_text"):
            continue
        if str(item.get("context_key") or "") in existing_context_keys:
            continue
        placeholders.append(item)
    return placeholders


def list_external_receipt_items(limit: int = 500) -> dict[str, Any]:
    ensure_external_product_candidates_schema()
    normalized_limit = max(1, min(int(limit or 500), 500))

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
        placeholders = _list_purchase_import_placeholders(conn, _candidate_context_keys(candidates), normalized_limit)

    combined = _apply_status_contract(candidates + placeholders)
    return {
        "items": combined[:normalized_limit],
        "candidate_rows": len(candidates),
        "purchase_import_line_rows": len(placeholders),
        "total": len(combined[:normalized_limit]),
        "status_contract": "explicit_backend_fields_v1",
    }


def ensure_external_receipt_item_candidates(items: list[dict[str, Any]] | None = None, include_below_threshold: bool = True) -> dict[str, Any]:
    normalized_items = [item for item in (items or []) if isinstance(item, dict)]
    processed = 0
    saved_count = 0
    updated_count = 0
    skipped_count = 0
    errors: list[dict[str, Any]] = []

    for item in normalized_items:
        receipt_line_text = str(item.get("receipt_line_text") or item.get("receiptLineText") or "").strip()
        retailer_code = str(item.get("retailer_code") or item.get("retailerCode") or "").strip().lower()
        purchase_import_line_id = str(item.get("purchase_import_line_id") or item.get("purchaseImportLineId") or "").strip() or None
        receipt_line_id = str(item.get("receipt_line_id") or item.get("receiptLineId") or "").strip() or None

        if not receipt_line_text:
            skipped_count += 1
            errors.append({"reason": "missing_receipt_line_text", "item": item})
            continue

        if not retailer_code or retailer_code in {"-", "import", "onbekend"}:
            retailer_code = "lidl"

        try:
            result = save_matchpreview_candidates(
                retailer_code=retailer_code,
                receipt_line_text=receipt_line_text,
                receipt_line_id=receipt_line_id,
                purchase_import_line_id=purchase_import_line_id,
                include_below_threshold=include_below_threshold,
            )
            processed += 1
            saved_count += int(result.get("saved_count") or 0)
            updated_count += int(result.get("updated_count") or 0)
            skipped_count += int(result.get("skipped_count") or 0)
        except Exception as exc:
            skipped_count += 1
            errors.append({"receipt_line_text": receipt_line_text, "retailer_code": retailer_code, "reason": str(exc)})

    return {
        "ok": True,
        "total": len(normalized_items),
        "processed": processed,
        "saved_count": saved_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "errors": errors,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def promote_external_product_candidate(candidate_id: str, force_overwrite: bool = False) -> dict[str, Any]:
    ensure_external_product_candidates_schema()
    normalized_candidate_id = str(candidate_id or "").strip()
    if not normalized_candidate_id:
        return {"ok": False, "promoted": False, "reason": "missing_candidate_id"}

    with engine.begin() as conn:
        candidate = conn.execute(
            text("SELECT * FROM external_product_candidates WHERE id = :candidate_id LIMIT 1"),
            {"candidate_id": normalized_candidate_id},
        ).mappings().first()
        if not candidate:
            return {"ok": False, "promoted": False, "reason": "candidate_not_found"}

        context_key = str(candidate.get("context_key") or "").strip()
        if not context_key:
            return {"ok": False, "promoted": False, "reason": "missing_context_key"}

        linked_rows = conn.execute(
            text(
                """
                SELECT id
                FROM external_product_candidates
                WHERE context_key = :context_key
                  AND id <> :candidate_id
                  AND (
                    candidate_status IN ('linked_to_catalog', 'user_confirmed')
                    OR status IN ('linked_to_catalog', 'user_confirmed')
                    OR is_user_confirmed = 1
                    OR is_external_database_override = 1
                  )
                """
            ),
            {"context_key": context_key, "candidate_id": normalized_candidate_id},
        ).mappings().all()

        if linked_rows and not force_overwrite:
            return {
                "ok": True,
                "promoted": False,
                "requires_overwrite": True,
                "existing_link_count": len(linked_rows),
                "candidate_id": normalized_candidate_id,
                "context_key": context_key,
            }

        conn.execute(
            text(
                """
                UPDATE external_product_candidates
                SET candidate_status = 'candidate',
                    status = 'candidate',
                    is_user_confirmed = 0,
                    is_external_database_override = 0,
                    global_product_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE context_key = :context_key
                  AND id <> :candidate_id
                """
            ),
            {"context_key": context_key, "candidate_id": normalized_candidate_id},
        )

        conn.execute(
            text(
                """
                UPDATE external_product_candidates
                SET candidate_status = 'linked_to_catalog',
                    status = 'linked_to_catalog',
                    is_user_confirmed = 1,
                    is_external_database_override = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :candidate_id
                """
            ),
            {"candidate_id": normalized_candidate_id},
        )

    return {
        "ok": True,
        "promoted": True,
        "requires_overwrite": False,
        "candidate_id": normalized_candidate_id,
        "context_key": context_key,
    }


def unlink_external_catalog_links(
    context_keys: list[str] | None = None,
    candidate_ids: list[str] | None = None,
) -> dict[str, Any]:
    ensure_external_product_candidates_schema()
    normalized_context_keys = [str(value).strip() for value in (context_keys or []) if str(value).strip()]
    normalized_candidate_ids = [str(value).strip() for value in (candidate_ids or []) if str(value).strip()]

    if not normalized_context_keys and not normalized_candidate_ids:
        return {"ok": True, "unlinked_count": 0, "purchase_import_line_unlinked_count": 0}

    where_parts: list[str] = []
    params: dict[str, Any] = {}
    if normalized_context_keys:
        keys = []
        for index, value in enumerate(normalized_context_keys):
            key = f"context_key_{index}"
            keys.append(f":{key}")
            params[key] = value
        where_parts.append(f"context_key IN ({', '.join(keys)})")

    if normalized_candidate_ids:
        keys = []
        for index, value in enumerate(normalized_candidate_ids):
            key = f"candidate_id_{index}"
            keys.append(f":{key}")
            params[key] = value
        where_parts.append(f"id IN ({', '.join(keys)})")

    where_sql = " OR ".join(where_parts)

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT id, purchase_import_line_id
                FROM external_product_candidates
                WHERE {where_sql}
                  AND (
                    global_product_id IS NOT NULL
                    OR status = 'linked_to_catalog'
                    OR candidate_status = 'linked_to_catalog'
                    OR is_user_confirmed = 1
                    OR is_external_database_override = 1
                  )
                """
            ),
            params,
        ).mappings().all()

        result = conn.execute(
            text(
                f"""
                UPDATE external_product_candidates
                SET global_product_id = NULL,
                    status = 'unlinked_from_catalog',
                    candidate_status = CASE
                        WHEN candidate_status = 'linked_to_catalog' THEN 'possible_candidate'
                        ELSE candidate_status
                    END,
                    is_user_confirmed = 0,
                    is_external_database_override = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE {where_sql}
                """
            ),
            params,
        )
        unlinked_count = int(result.rowcount or 0)

        purchase_import_line_ids = [
            str(row.get("purchase_import_line_id") or "").strip()
            for row in rows
            if str(row.get("purchase_import_line_id") or "").strip()
        ]
        for context_key in normalized_context_keys:
            if context_key.startswith("purchase-import-line:"):
                purchase_import_line_ids.append(context_key.replace("purchase-import-line:", "", 1).strip())

        purchase_import_line_ids = sorted({value for value in purchase_import_line_ids if value})
        purchase_import_line_unlinked_count = 0

        if purchase_import_line_ids and _table_exists(conn, "purchase_import_lines"):
            columns = _table_columns(conn, "purchase_import_lines")
            if "matched_global_product_id" in columns:
                id_params = {}
                id_keys = []
                for index, value in enumerate(purchase_import_line_ids):
                    key = f"purchase_import_line_id_{index}"
                    id_keys.append(f":{key}")
                    id_params[key] = value
                update_result = conn.execute(
                    text(
                        f"""
                        UPDATE purchase_import_lines
                        SET matched_global_product_id = NULL
                        WHERE id IN ({', '.join(id_keys)})
                        """
                    ),
                    id_params,
                )
                purchase_import_line_unlinked_count = int(update_result.rowcount or 0)

    return {
        "ok": True,
        "unlinked_count": unlinked_count,
        "purchase_import_line_unlinked_count": purchase_import_line_unlinked_count,
    }
