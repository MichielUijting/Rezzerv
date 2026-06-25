from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_product_candidate_store import (
    _m2c2h5_table_columns,
    _m2c2h5_table_exists,
    build_candidate_context_key,
    ensure_external_product_candidates_schema,
)

M2C2I22_CONFIRMED_STATUS = "external_resolved"
M2C2I22_USER_CONFIRMED_STATUS = "user_confirmed"


def _truthy(value: Any) -> bool:
    normalized = str(value if value is not None else "").strip().lower()
    return bool(normalized and normalized not in {"-", "0", "none", "null", "undefined", "false", "unknown", "onbekend"})


def _first_truthy(row: dict[str, Any], *field_names: str) -> str:
    for field_name in field_names:
        value = str(row.get(field_name) if row.get(field_name) is not None else "").strip()
        if _truthy(value):
            return value
    return ""


def _candidate_external_code(candidate: dict[str, Any]) -> str:
    return _first_truthy(
        candidate,
        "external_source_product_code",
        "candidate_source_product_code",
        "source_product_code",
        "retailer_article_number",
        "gtin",
        "ean",
        "code",
    )


def _candidate_source_name(candidate: dict[str, Any]) -> str:
    return _first_truthy(candidate, "external_source_name", "candidate_source_name", "source_name") or "external_candidate"


def _candidate_receipt_text(candidate: dict[str, Any]) -> str:
    return _first_truthy(candidate, "receipt_line_text", "candidate_name")


def _candidate_context_key(candidate: dict[str, Any]) -> str:
    context_key = _first_truthy(candidate, "context_key")
    if context_key:
        return context_key
    return build_candidate_context_key(
        str(candidate.get("retailer_code") or "").strip().lower(),
        _candidate_receipt_text(candidate),
        receipt_line_id=_first_truthy(candidate, "receipt_line_id") or None,
        purchase_import_line_id=_first_truthy(candidate, "purchase_import_line_id") or None,
    )


def _set_sql_fragment(column_names: list[str]) -> str:
    return ",\n                        ".join(f"{column_name} = :{column_name}" for column_name in column_names)


def _update_purchase_import_line(conn, purchase_import_line_id: str, external_code: str, source_name: str, candidate: dict[str, Any]) -> int:
    if not purchase_import_line_id or not _m2c2h5_table_exists(conn, "purchase_import_lines"):
        return 0

    columns = _m2c2h5_table_columns(conn, "purchase_import_lines")
    updates: dict[str, Any] = {}

    for column_name in ("external_article_code", "external_product_code", "retailer_article_number"):
        if column_name in columns:
            updates[column_name] = external_code

    for column_name in ("external_source_name", "source_name", "external_product_source"):
        if column_name in columns:
            updates[column_name] = source_name

    for column_name in ("external_match_status", "status"):
        if column_name in columns:
            updates[column_name] = M2C2I22_CONFIRMED_STATUS

    if "matched_external_candidate_id" in columns:
        updates["matched_external_candidate_id"] = str(candidate.get("id") or "").strip()
    if "matched_external_candidate_name" in columns:
        updates["matched_external_candidate_name"] = str(candidate.get("candidate_name") or "").strip()
    if "updated_at" in columns:
        updates["updated_at"] = _now_timestamp_sql(conn)

    if not updates:
        return 0

    inline_timestamp_columns = {name for name, value in updates.items() if value == "__CURRENT_TIMESTAMP__"}
    param_updates = {name: value for name, value in updates.items() if name not in inline_timestamp_columns}
    assignments = [f"{name} = CURRENT_TIMESTAMP" for name in inline_timestamp_columns]
    assignments.extend(f"{name} = :{name}" for name in param_updates)

    result = conn.execute(
        text(
            f"""
            UPDATE purchase_import_lines
            SET {', '.join(assignments)}
            WHERE id = :purchase_import_line_id
            """
        ),
        {**param_updates, "purchase_import_line_id": purchase_import_line_id},
    )
    return int(result.rowcount or 0)


def _update_receipt_line(conn, receipt_line_id: str, external_code: str, source_name: str, candidate: dict[str, Any]) -> int:
    if not receipt_line_id or not _m2c2h5_table_exists(conn, "receipt_lines"):
        return 0

    columns = _m2c2h5_table_columns(conn, "receipt_lines")
    updates: dict[str, Any] = {}

    for column_name in ("external_article_code", "external_product_code", "retailer_article_number"):
        if column_name in columns:
            updates[column_name] = external_code

    for column_name in ("external_source_name", "source_name", "external_product_source"):
        if column_name in columns:
            updates[column_name] = source_name

    for column_name in ("external_match_status", "status"):
        if column_name in columns:
            updates[column_name] = M2C2I22_CONFIRMED_STATUS

    if "matched_external_candidate_id" in columns:
        updates["matched_external_candidate_id"] = str(candidate.get("id") or "").strip()
    if "matched_external_candidate_name" in columns:
        updates["matched_external_candidate_name"] = str(candidate.get("candidate_name") or "").strip()
    if "updated_at" in columns:
        updates["updated_at"] = _now_timestamp_sql(conn)

    if not updates:
        return 0

    inline_timestamp_columns = {name for name, value in updates.items() if value == "__CURRENT_TIMESTAMP__"}
    param_updates = {name: value for name, value in updates.items() if name not in inline_timestamp_columns}
    assignments = [f"{name} = CURRENT_TIMESTAMP" for name in inline_timestamp_columns]
    assignments.extend(f"{name} = :{name}" for name in param_updates)

    result = conn.execute(
        text(
            f"""
            UPDATE receipt_lines
            SET {', '.join(assignments)}
            WHERE id = :receipt_line_id
            """
        ),
        {**param_updates, "receipt_line_id": receipt_line_id},
    )
    return int(result.rowcount or 0)


def _now_timestamp_sql(conn) -> str:
    return "__CURRENT_TIMESTAMP__"


def confirm_external_candidate_for_receipt_item(candidate_id: str, force_overwrite: bool = False) -> dict[str, Any]:
    """Bevestig een externe kandidaat op de bonregel zonder catalogus-/voorraadmutaties.

    M2C2i-22 legt alleen de externe artikelcode en bron vast op de bonregel/importregel.
    De functie maakt geen global_products, geen Mijn artikel en geen voorraadmutatie.
    """
    ensure_external_product_candidates_schema()
    normalized_candidate_id = str(candidate_id or "").strip()
    if not normalized_candidate_id:
        return {"ok": False, "confirmed": False, "reason": "missing_candidate_id"}

    with engine.begin() as conn:
        candidate_row = conn.execute(
            text(
                """
                SELECT *
                FROM external_product_candidates
                WHERE id = :candidate_id
                LIMIT 1
                """
            ),
            {"candidate_id": normalized_candidate_id},
        ).mappings().first()

        if not candidate_row:
            return {"ok": False, "confirmed": False, "reason": "candidate_not_found"}

        candidate = dict(candidate_row)
        external_code = _candidate_external_code(candidate)
        if not external_code:
            return {"ok": False, "confirmed": False, "reason": "missing_external_product_code", "candidate_id": normalized_candidate_id}

        context_key = _candidate_context_key(candidate)
        purchase_import_line_id = _first_truthy(candidate, "purchase_import_line_id")
        receipt_line_id = _first_truthy(candidate, "receipt_line_id")
        source_name = _candidate_source_name(candidate)

        linked_rows = conn.execute(
            text(
                """
                SELECT id
                FROM external_product_candidates
                WHERE context_key = :context_key
                  AND id <> :candidate_id
                  AND (
                    candidate_status IN ('external_resolved', 'user_confirmed', 'linked_to_catalog')
                    OR status IN ('external_resolved', 'user_confirmed', 'linked_to_catalog')
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
                "confirmed": False,
                "requires_overwrite": True,
                "existing_link_count": len(linked_rows),
                "candidate_id": normalized_candidate_id,
                "context_key": context_key,
                "creates_global_product": False,
                "creates_household_article": False,
                "creates_inventory_event": False,
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
                SET candidate_status = :candidate_status,
                    status = :status,
                    is_user_confirmed = 1,
                    is_external_database_override = 0,
                    global_product_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :candidate_id
                """
            ),
            {
                "candidate_id": normalized_candidate_id,
                "candidate_status": M2C2I22_USER_CONFIRMED_STATUS,
                "status": M2C2I22_CONFIRMED_STATUS,
            },
        )

        purchase_import_line_updated_count = _update_purchase_import_line(
            conn,
            purchase_import_line_id,
            external_code,
            source_name,
            candidate,
        )
        receipt_line_updated_count = _update_receipt_line(
            conn,
            receipt_line_id,
            external_code,
            source_name,
            candidate,
        )

    return {
        "ok": True,
        "confirmed": True,
        "requires_overwrite": False,
        "candidate_id": normalized_candidate_id,
        "context_key": context_key,
        "purchase_import_line_id": purchase_import_line_id or None,
        "receipt_line_id": receipt_line_id or None,
        "external_product_code": external_code,
        "external_source_name": source_name,
        "purchase_import_line_updated_count": purchase_import_line_updated_count,
        "receipt_line_updated_count": receipt_line_updated_count,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
