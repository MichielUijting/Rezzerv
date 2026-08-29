from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, text

from app.db import engine
from app.services.external_product_candidate_store import (
    build_candidate_context_key,
    ensure_external_product_candidates_schema,
)

EXTERNAL_RECOGNITION_STATUS = "external_resolved"
CATALOG_LINK_STATUS = "linked_to_catalog"

_FALLBACK_MARKERS = (
    "fallback",
    "unresolved",
    "no_external_match",
    "receipt_product_intent_fallback",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    normalized = _text(value).lower()
    return bool(
        normalized
        and normalized
        not in {
            "-",
            "0",
            "none",
            "null",
            "undefined",
            "false",
            "unknown",
            "onbekend",
        }
    )


def _table_exists(conn, table_name: str) -> bool:
    return bool(inspect(conn).has_table(table_name))


def _table_columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {
        _text(column.get("name"))
        for column in inspect(conn).get_columns(table_name)
        if _text(column.get("name"))
    }


def _candidate_external_code(candidate: dict[str, Any]) -> str:
    for field_name in (
        "external_source_product_code",
        "candidate_source_product_code",
        "source_product_code",
        "retailer_article_number",
        "gtin",
        "ean",
        "code",
    ):
        value = _text(candidate.get(field_name))
        if _truthy(value):
            return value
    return ""


def _candidate_source_name(candidate: dict[str, Any]) -> str:
    for field_name in (
        "external_source_name",
        "candidate_source_name",
        "source_name",
    ):
        value = _text(candidate.get(field_name))
        if _truthy(value):
            return value
    return "external_candidate"


def _candidate_is_fallback(candidate: dict[str, Any]) -> bool:
    haystack = " ".join(
        _text(candidate.get(field_name)).lower()
        for field_name in (
            "candidate_status",
            "status",
            "candidate_source_name",
            "source_name",
            "candidate_source_product_code",
            "source_product_code",
            "variant",
        )
    )
    return any(marker in haystack for marker in _FALLBACK_MARKERS)


def _candidate_context_key(candidate: dict[str, Any]) -> str:
    explicit = _text(candidate.get("context_key"))
    if explicit:
        return explicit
    return build_candidate_context_key(
        _text(candidate.get("retailer_code")).lower(),
        _text(candidate.get("receipt_line_text")) or _text(candidate.get("candidate_name")),
        receipt_line_id=_text(candidate.get("receipt_line_id")) or None,
        purchase_import_line_id=_text(candidate.get("purchase_import_line_id")) or None,
    )


def _append_if_column(
    updates: dict[str, Any],
    columns: set[str],
    column_name: str,
    value: Any,
) -> None:
    if column_name in columns:
        updates[column_name] = value


def _update_row(
    conn,
    table_name: str,
    row_id: str,
    updates: dict[str, Any],
) -> int:
    if not row_id or not updates or not _table_exists(conn, table_name):
        return 0

    columns = _table_columns(conn, table_name)
    if "id" not in columns:
        return 0

    filtered = {key: value for key, value in updates.items() if key in columns}
    if not filtered:
        return 0

    assignments: list[str] = []
    params: dict[str, Any] = {"row_id": row_id}
    for key, value in filtered.items():
        if value == "__CURRENT_TIMESTAMP__":
            assignments.append(f"{key} = CURRENT_TIMESTAMP")
        else:
            assignments.append(f"{key} = :{key}")
            params[key] = value

    result = conn.execute(
        text(
            f"UPDATE {table_name} "
            f"SET {', '.join(assignments)} "
            "WHERE id = :row_id"
        ),
        params,
    )
    return int(result.rowcount or 0)


def _receipt_item_updates(external_code: str, source_name: str) -> dict[str, Any]:
    return {
        "external_article_code": external_code,
        "external_product_code": external_code,
        "retailer_article_number": external_code,
        "external_source_name": source_name,
        "source_name": source_name,
        "external_product_source": source_name,
        "external_match_status": EXTERNAL_RECOGNITION_STATUS,
        "updated_at": "__CURRENT_TIMESTAMP__",
    }


def _recognition_candidate_where(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    where_parts: list[str] = []
    params: dict[str, Any] = {"recognition_status": EXTERNAL_RECOGNITION_STATUS}

    context_key = _text(item.get("context_key"))
    receipt_line_id = _text(item.get("receipt_line_id") or item.get("receiptLineId"))
    purchase_import_line_id = _text(
        item.get("purchase_import_line_id") or item.get("purchaseImportLineId")
    )

    if context_key:
        where_parts.append("context_key = :context_key")
        params["context_key"] = context_key
    if receipt_line_id:
        where_parts.append("receipt_line_id = :receipt_line_id")
        params["receipt_line_id"] = receipt_line_id
    if purchase_import_line_id:
        where_parts.append("purchase_import_line_id = :purchase_import_line_id")
        params["purchase_import_line_id"] = purchase_import_line_id

    if not where_parts:
        retailer_code = _text(item.get("retailer_code") or item.get("retailerCode")).lower()
        receipt_line_text = _text(
            item.get("receipt_line_text") or item.get("receiptLineText")
        )
        if retailer_code and receipt_line_text:
            params["fallback_context_key"] = build_candidate_context_key(
                retailer_code,
                receipt_line_text,
            )
            where_parts.append("context_key = :fallback_context_key")

    return " OR ".join(where_parts), params


def get_external_recognition_state(item: dict[str, Any] | None) -> dict[str, Any]:
    """Return the confirmed external-recognition state for one receipt item.

    A recognition is deliberately distinct from a Catalogus link. Only the explicit
    `external_resolved` state counts here; a projected retailer/source code by itself
    is not enough to mark an item as confirmed.
    """
    if not isinstance(item, dict):
        return {"resolved": False}

    explicit_statuses = {
        _text(item.get("status")).lower(),
        _text(item.get("candidate_status")).lower(),
        _text(item.get("external_match_status")).lower(),
    }
    if EXTERNAL_RECOGNITION_STATUS in explicit_statuses:
        return {
            "resolved": True,
            "candidate_id": _text(item.get("candidate_id") or item.get("id")) or None,
            "external_product_code": _candidate_external_code(item) or None,
            "external_source_name": _candidate_source_name(item),
        }

    ensure_external_product_candidates_schema()
    where_sql, params = _recognition_candidate_where(item)
    if not where_sql:
        return {"resolved": False}

    with engine.begin() as conn:
        row = conn.execute(
            text(
                f"""
                SELECT *
                FROM external_product_candidates
                WHERE ({where_sql})
                  AND (
                    status = :recognition_status
                    OR candidate_status = :recognition_status
                  )
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """
            ),
            params,
        ).mappings().first()

    if not row:
        return {"resolved": False}

    candidate = dict(row)
    return {
        "resolved": True,
        "candidate_id": _text(candidate.get("id")) or None,
        "external_product_code": _candidate_external_code(candidate) or None,
        "external_source_name": _candidate_source_name(candidate),
    }


def is_external_recognition_resolved_item(item: dict[str, Any] | None) -> bool:
    return bool(get_external_recognition_state(item).get("resolved"))


def confirm_external_recognition(
    candidate_id: str,
    force_overwrite: bool = False,
) -> dict[str, Any]:
    """Confirm an external recognition without creating Catalogus or inventory data.

    The selected external candidate receives the explicit `external_resolved` state.
    This state is intentionally *not* `user_confirmed`, because current Catalogus
    compatibility code treats `user_confirmed` as a catalog-link signal.
    """
    ensure_external_product_candidates_schema()
    normalized_candidate_id = _text(candidate_id)
    if not normalized_candidate_id:
        return {"ok": False, "confirmed": False, "reason": "missing_candidate_id"}

    with engine.begin() as conn:
        row = conn.execute(
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

        if not row:
            return {"ok": False, "confirmed": False, "reason": "candidate_not_found"}

        candidate = dict(row)
        status_values = {
            _text(candidate.get("status")).lower(),
            _text(candidate.get("candidate_status")).lower(),
        }
        if CATALOG_LINK_STATUS in status_values or _truthy(candidate.get("global_product_id")):
            return {
                "ok": True,
                "confirmed": False,
                "reason": "candidate_already_linked_to_catalog",
                "candidate_id": normalized_candidate_id,
                "creates_global_product": False,
                "creates_product_identity": False,
                "creates_household_article": False,
                "creates_inventory_event": False,
            }

        if _candidate_is_fallback(candidate):
            return {
                "ok": False,
                "confirmed": False,
                "reason": "fallback_candidate_cannot_be_confirmed",
                "candidate_id": normalized_candidate_id,
            }

        external_code = _candidate_external_code(candidate)
        if not external_code:
            return {
                "ok": False,
                "confirmed": False,
                "reason": "missing_external_product_code",
                "candidate_id": normalized_candidate_id,
            }

        context_key = _candidate_context_key(candidate)
        source_name = _candidate_source_name(candidate)
        receipt_line_id = _text(candidate.get("receipt_line_id"))
        purchase_import_line_id = _text(candidate.get("purchase_import_line_id"))

        if EXTERNAL_RECOGNITION_STATUS in status_values:
            return {
                "ok": True,
                "confirmed": True,
                "already_confirmed": True,
                "requires_overwrite": False,
                "candidate_id": normalized_candidate_id,
                "context_key": context_key,
                "external_product_code": external_code,
                "external_source_name": source_name,
                "creates_global_product": False,
                "creates_product_identity": False,
                "creates_household_article": False,
                "creates_inventory_event": False,
            }

        existing_rows = conn.execute(
            text(
                """
                SELECT id
                FROM external_product_candidates
                WHERE context_key = :context_key
                  AND id <> :candidate_id
                  AND (
                    status = :recognition_status
                    OR candidate_status = :recognition_status
                  )
                """
            ),
            {
                "context_key": context_key,
                "candidate_id": normalized_candidate_id,
                "recognition_status": EXTERNAL_RECOGNITION_STATUS,
            },
        ).mappings().all()

        if existing_rows and not force_overwrite:
            return {
                "ok": True,
                "confirmed": False,
                "requires_overwrite": True,
                "existing_recognition_count": len(existing_rows),
                "candidate_id": normalized_candidate_id,
                "context_key": context_key,
                "creates_global_product": False,
                "creates_product_identity": False,
                "creates_household_article": False,
                "creates_inventory_event": False,
            }

        if existing_rows:
            conn.execute(
                text(
                    """
                    UPDATE external_product_candidates
                    SET status = CASE
                            WHEN status = :recognition_status THEN 'candidate'
                            ELSE status
                        END,
                        candidate_status = CASE
                            WHEN candidate_status = :recognition_status THEN 'candidate'
                            ELSE candidate_status
                        END,
                        is_user_confirmed = FALSE,
                        is_external_database_override = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE context_key = :context_key
                      AND id <> :candidate_id
                      AND (
                        status = :recognition_status
                        OR candidate_status = :recognition_status
                      )
                    """
                ),
                {
                    "context_key": context_key,
                    "candidate_id": normalized_candidate_id,
                    "recognition_status": EXTERNAL_RECOGNITION_STATUS,
                },
            )

        conn.execute(
            text(
                """
                UPDATE external_product_candidates
                SET status = :recognition_status,
                    candidate_status = :recognition_status,
                    is_user_confirmed = FALSE,
                    is_external_database_override = FALSE,
                    global_product_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :candidate_id
                """
            ),
            {
                "candidate_id": normalized_candidate_id,
                "recognition_status": EXTERNAL_RECOGNITION_STATUS,
            },
        )

        updates = _receipt_item_updates(external_code, source_name)
        purchase_import_line_updated_count = _update_row(
            conn,
            "purchase_import_lines",
            purchase_import_line_id,
            updates,
        )
        receipt_table_line_updated_count = _update_row(
            conn,
            "receipt_table_lines",
            receipt_line_id,
            updates,
        )
        legacy_receipt_line_updated_count = _update_row(
            conn,
            "receipt_lines",
            receipt_line_id,
            updates,
        )

    return {
        "ok": True,
        "confirmed": True,
        "already_confirmed": False,
        "requires_overwrite": False,
        "candidate_id": normalized_candidate_id,
        "context_key": context_key,
        "receipt_line_id": receipt_line_id or None,
        "purchase_import_line_id": purchase_import_line_id or None,
        "external_product_code": external_code,
        "external_source_name": source_name,
        "purchase_import_line_updated_count": purchase_import_line_updated_count,
        "receipt_table_line_updated_count": receipt_table_line_updated_count,
        "legacy_receipt_line_updated_count": legacy_receipt_line_updated_count,
        "creates_global_product": False,
        "creates_product_identity": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
