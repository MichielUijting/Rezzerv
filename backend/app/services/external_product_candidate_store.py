from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_database_matchers import match_retailer_receipt_line

PROTECTED_CANDIDATE_STATUSES = {
    "user_confirmed",
    "external_database_override",
}

CANDIDATE_COLUMNS: dict[str, str] = {
    "id": "TEXT PRIMARY KEY",
    "receipt_line_id": "TEXT",
    "purchase_import_line_id": "TEXT",
    "context_key": "TEXT",
    "retailer_code": "TEXT",
    "receipt_line_text": "TEXT",
    "candidate_name": "TEXT",
    "candidate_brand": "TEXT",
    "candidate_source_name": "TEXT",
    "candidate_source_product_code": "TEXT",
    "source_name": "TEXT",
    "source_product_code": "TEXT",
    "retailer_article_number": "TEXT",
    "quantity_label": "TEXT",
    "variant": "TEXT",
    "source_url": "TEXT",
    "score": "REAL",
    "score_breakdown_json": "TEXT",
    "global_product_id": "TEXT",
    "status": "TEXT",
    "candidate_status": "TEXT",
    "is_probable": "INTEGER DEFAULT 0",
    "is_user_confirmed": "INTEGER DEFAULT 0",
    "is_external_database_override": "INTEGER DEFAULT 0",
    "created_by": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}

CREATE_EXTERNAL_PRODUCT_CANDIDATES_SQL = """
CREATE TABLE IF NOT EXISTS external_product_candidates (
    id TEXT PRIMARY KEY,
    receipt_line_id TEXT,
    purchase_import_line_id TEXT,
    context_key TEXT,
    retailer_code TEXT,
    receipt_line_text TEXT,
    candidate_name TEXT,
    candidate_brand TEXT,
    candidate_source_name TEXT,
    candidate_source_product_code TEXT,
    source_name TEXT,
    source_product_code TEXT,
    retailer_article_number TEXT,
    quantity_label TEXT,
    variant TEXT,
    source_url TEXT,
    score REAL,
    score_breakdown_json TEXT,
    candidate_status TEXT,
    is_probable INTEGER DEFAULT 0,
    is_user_confirmed INTEGER DEFAULT 0,
    is_external_database_override INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TEXT,
    updated_at TEXT
)
"""

CREATE_EXTERNAL_PRODUCT_CANDIDATES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_external_product_candidates_context
ON external_product_candidates (context_key, retailer_code, candidate_source_name, candidate_source_product_code, variant)
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_candidate_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def build_candidate_context_key(retailer_code: str, receipt_line_text: str, receipt_line_id: str | None = None, purchase_import_line_id: str | None = None) -> str:
    if receipt_line_id:
        return f"receipt-line:{receipt_line_id}"
    if purchase_import_line_id:
        return f"purchase-import-line:{purchase_import_line_id}"
    return f"external-preview:{normalize_candidate_text(retailer_code)}:{normalize_candidate_text(receipt_line_text)}"


def build_preview_import_line_fallback(context_key: str) -> str:
    return f"preview:{context_key}"


def _get_sqlite_columns(conn) -> set[str]:
    rows = conn.execute(text("PRAGMA table_info(external_product_candidates)")).mappings().all()
    return {str(row.get("name") or "") for row in rows}


def _get_postgres_columns(conn) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'external_product_candidates'
            """
        )
    ).mappings().all()
    return {str(row.get("column_name") or "") for row in rows}


def _add_missing_columns(conn) -> None:
    dialect_name = str(engine.dialect.name or "").lower()
    existing_columns = _get_sqlite_columns(conn) if dialect_name == "sqlite" else _get_postgres_columns(conn)
    for column_name, column_definition in CANDIDATE_COLUMNS.items():
        if column_name in existing_columns:
            continue
        if column_name == "id":
            continue
        conn.execute(text(f"ALTER TABLE external_product_candidates ADD COLUMN {column_name} {column_definition}"))


def ensure_external_product_candidates_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text(CREATE_EXTERNAL_PRODUCT_CANDIDATES_SQL))
        _add_missing_columns(conn)
        conn.execute(text(CREATE_EXTERNAL_PRODUCT_CANDIDATES_INDEX_SQL))


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, str]:
    return {
        "candidate_source_name": str(candidate.get("candidate_source_name") or "").strip(),
        "candidate_source_product_code": str(candidate.get("candidate_source_product_code") or candidate.get("retailer_article_number") or "").strip(),
        "variant": str(candidate.get("variant") or "").strip(),
        "candidate_name": str(candidate.get("candidate_name") or "").strip(),
    }


def _find_existing_candidate(conn, context_key: str, retailer_code: str, candidate: dict[str, Any]):
    identity = _candidate_identity(candidate)
    return conn.execute(
        text(
            """
            SELECT id, candidate_status, is_user_confirmed, is_external_database_override
            FROM external_product_candidates
            WHERE COALESCE(context_key, '') = COALESCE(:context_key, '')
              AND COALESCE(retailer_code, '') = COALESCE(:retailer_code, '')
              AND COALESCE(candidate_source_name, COALESCE(source_name, '')) = COALESCE(:candidate_source_name, '')
              AND COALESCE(candidate_source_product_code, COALESCE(source_product_code, '')) = COALESCE(:candidate_source_product_code, '')
              AND COALESCE(variant, '') = COALESCE(:variant, '')
              AND COALESCE(candidate_name, '') = COALESCE(:candidate_name, '')
            LIMIT 1
            """
        ),
        {
            "context_key": context_key,
            "retailer_code": retailer_code,
            **identity,
        },
    ).mappings().first()


def _is_protected(existing: dict[str, Any] | None) -> bool:
    if not existing:
        return False
    status = str(existing.get("candidate_status") or "").strip()
    return (
        status in PROTECTED_CANDIDATE_STATUSES
        or bool(existing.get("is_user_confirmed"))
        or bool(existing.get("is_external_database_override"))
    )


def _serialize_score_breakdown(candidate: dict[str, Any]) -> str:
    return json.dumps(candidate.get("score_breakdown") or {}, ensure_ascii=False, sort_keys=True)


def save_matchpreview_candidates(
    retailer_code: str,
    receipt_line_text: str,
    receipt_line_id: str | None = None,
    purchase_import_line_id: str | None = None,
    include_below_threshold: bool = False,
) -> dict[str, Any]:
    ensure_external_product_candidates_schema()

    match_result = match_retailer_receipt_line(
        retailer_code=retailer_code,
        receipt_line_text=receipt_line_text,
        include_below_threshold=include_below_threshold,
    )
    normalized_retailer = str(match_result.get("retailer_code") or retailer_code or "").strip().lower()
    context_key = build_candidate_context_key(
        normalized_retailer,
        receipt_line_text,
        receipt_line_id=receipt_line_id,
        purchase_import_line_id=purchase_import_line_id,
    )
    storage_purchase_import_line_id = purchase_import_line_id or build_preview_import_line_fallback(context_key)
    candidates = list(match_result.get("candidates") or [])
    timestamp = now_iso()
    saved = []
    skipped = []
    updated = []

    with engine.begin() as conn:
        for candidate in candidates:
            existing = _find_existing_candidate(conn, context_key, normalized_retailer, candidate)
            if _is_protected(existing):
                skipped.append({"id": existing.get("id"), "reason": "protected_candidate"})
                continue

            candidate_id = str(existing.get("id")) if existing else str(uuid.uuid4())
            candidate_source_name = str(candidate.get("candidate_source_name") or "external_database").strip()
            candidate_source_product_code = str(candidate.get("candidate_source_product_code") or candidate.get("retailer_article_number") or "unknown").strip()
            params = {
                "id": candidate_id,
                "receipt_line_id": receipt_line_id,
                "purchase_import_line_id": storage_purchase_import_line_id,
                "context_key": context_key,
                "retailer_code": normalized_retailer,
                "receipt_line_text": receipt_line_text,
                "candidate_name": str(candidate.get("candidate_name") or "").strip(),
                "candidate_brand": str(candidate.get("candidate_brand") or "").strip() or None,
                "candidate_source_name": candidate_source_name,
                "candidate_source_product_code": candidate_source_product_code,
                "source_name": candidate_source_name,
                "source_product_code": candidate_source_product_code,
                "retailer_article_number": str(candidate.get("retailer_article_number") or "").strip() or None,
                "quantity_label": str(candidate.get("quantity_label") or "").strip() or None,
                "variant": str(candidate.get("variant") or "").strip() or None,
                "source_url": str(candidate.get("source_url") or "").strip() or None,
                "score": float(candidate.get("score") or 0),
                "score_breakdown_json": _serialize_score_breakdown(candidate),
                "candidate_status": str(candidate.get("candidate_status") or "possible_candidate").strip(),
                "is_probable": 1 if bool(candidate.get("is_probable")) else 0,
                "is_user_confirmed": 0,
                "is_external_database_override": 0,
                "created_by": str(candidate.get("created_by") or "external_database_matchpreview_save_v1").strip(),
                "created_at": timestamp,
                "updated_at": timestamp,
            }

            if existing:
                conn.execute(
                    text(
                        """
                        UPDATE external_product_candidates
                        SET receipt_line_id = :receipt_line_id,
                            purchase_import_line_id = :purchase_import_line_id,
                            receipt_line_text = :receipt_line_text,
                            candidate_brand = :candidate_brand,
                            candidate_source_name = :candidate_source_name,
                            candidate_source_product_code = :candidate_source_product_code,
                            source_name = :source_name,
                            source_product_code = :source_product_code,
                            retailer_article_number = :retailer_article_number,
                            quantity_label = :quantity_label,
                            source_url = :source_url,
                            score = :score,
                            score_breakdown_json = :score_breakdown_json,
                            candidate_status = :candidate_status,
                            is_probable = :is_probable,
                            updated_at = :updated_at
                        WHERE id = :id
                        """
                    ),
                    params,
                )
                updated.append(candidate_id)
            else:
                conn.execute(
                    text(
                        """
                        INSERT INTO external_product_candidates (
                            id,
                            receipt_line_id,
                            purchase_import_line_id,
                            context_key,
                            retailer_code,
                            receipt_line_text,
                            candidate_name,
                            candidate_brand,
                            candidate_source_name,
                            candidate_source_product_code,
                            source_name,
                            source_product_code,
                            retailer_article_number,
                            quantity_label,
                            variant,
                            source_url,
                            score,
                            score_breakdown_json,
                            candidate_status,
                            is_probable,
                            is_user_confirmed,
                            is_external_database_override,
                            created_by,
                            created_at,
                            updated_at
                        ) VALUES (
                            :id,
                            :receipt_line_id,
                            :purchase_import_line_id,
                            :context_key,
                            :retailer_code,
                            :receipt_line_text,
                            :candidate_name,
                            :candidate_brand,
                            :candidate_source_name,
                            :candidate_source_product_code,
                            :source_name,
                            :source_product_code,
                            :retailer_article_number,
                            :quantity_label,
                            :variant,
                            :source_url,
                            :score,
                            :score_breakdown_json,
                            :candidate_status,
                            :is_probable,
                            :is_user_confirmed,
                            :is_external_database_override,
                            :created_by,
                            :created_at,
                            :updated_at
                        )
                        """
                    ),
                    params,
                )
                saved.append(candidate_id)

    return {
        "ok": True,
        "context_key": context_key,
        "retailer_code": normalized_retailer,
        "receipt_line_text": receipt_line_text,
        "candidate_count": len(candidates),
        "saved_count": len(saved),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "saved_candidate_ids": saved,
        "updated_candidate_ids": updated,
        "skipped": skipped,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def list_saved_external_product_candidates(context_key: str | None = None, limit: int = 50) -> dict[str, Any]:
    ensure_external_product_candidates_schema()
    normalized_limit = max(1, min(int(limit or 50), 200))
    with engine.begin() as conn:
        if context_key:
            rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM external_product_candidates
                    WHERE context_key = :context_key
                    ORDER BY score DESC, updated_at DESC
                    LIMIT :limit
                    """
                ),
                {"context_key": context_key, "limit": normalized_limit},
            ).mappings().all()
        else:
            rows = conn.execute(
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
    return {"items": [dict(row) for row in rows]}


# M2C2h-5 receipt item overview and unlink support

def _table_exists(conn, table_name: str) -> bool:
    dialect_name = str(engine.dialect.name or "").lower()
    if dialect_name == "sqlite":
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
            {"table_name": table_name},
        ).first()
        return row is not None

    row = conn.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = :table_name
            LIMIT 1
            """
        ),
        {"table_name": table_name},
    ).first()
    return row is not None


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


def _first_existing_column(columns: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _column_expr(alias: str, columns: set[str], candidates: list[str], fallback: str = "''") -> str:
    column_name = _first_existing_column(columns, candidates)
    if not column_name:
        return fallback
    return f"{alias}.{column_name}"


def _candidate_context_keys(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("context_key") or "").strip() for row in rows if str(row.get("context_key") or "").strip()}


def _build_receipt_line_placeholder(row: dict[str, Any]) -> dict[str, Any]:
    receipt_line_id = str(row.get("receipt_line_id") or "").strip()
    retailer_code = str(row.get("retailer_code") or "").strip().lower()
    receipt_line_text = str(row.get("receipt_line_text") or "").strip()
    context_key = build_candidate_context_key(
        retailer_code or "onbekend",
        receipt_line_text,
        receipt_line_id=receipt_line_id or None,
    )

    receipt_item_id = f"receipt-line:{receipt_line_id}" if receipt_line_id else ""
    return {
        "id": receipt_item_id,
        "receipt_item_id": receipt_item_id,
        "receipt_item_type": "receipt_line",
        "receipt_item_source_id": receipt_line_id or None,
        "receipt_line_id": receipt_line_id or None,
        "purchase_import_line_id": str(row.get("purchase_import_line_id") or "").strip() or None,
        "context_key": context_key,
        "retailer_code": retailer_code or "onbekend",
        "receipt_line_text": receipt_line_text,
        "candidate_name": "",
        "candidate_brand": "",
        "candidate_source_name": "",
        "candidate_source_product_code": "",
        "source_name": "",
        "source_product_code": "",
        "retailer_article_number": str(row.get("retailer_article_number") or "").strip() or None,
        "quantity_label": str(row.get("quantity_label") or "").strip() or None,
        "variant": "",
        "source_url": "",
        "score": 0,
        "score_breakdown_json": "{}",
        "candidate_status": "no_candidate",
        "global_product_id": str(row.get("global_product_id") or "").strip() or None,
        "status": "linked_to_catalog" if str(row.get("global_product_id") or "").strip() else "no_candidate",
        "is_probable": 0,
        "is_user_confirmed": 0,
        "is_external_database_override": 0,
        "is_receipt_item_placeholder": True,
        "created_by": "receipt_lines",
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _list_receipt_line_placeholders(conn, existing_context_keys: set[str], limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "receipt_lines"):
        return []

    receipt_columns = _table_columns(conn, "receipt_lines")
    receipts_exists = _table_exists(conn, "receipts")
    receipts_columns = _table_columns(conn, "receipts") if receipts_exists else set()

    id_expr = _column_expr("rl", receipt_columns, ["id"], "''")
    text_expr = "COALESCE({}, '')".format(_column_expr("rl", receipt_columns, ["parsed_name", "raw_text"], "''"))
    raw_expr = _column_expr("rl", receipt_columns, ["raw_text"], "''")
    barcode_expr = _column_expr("rl", receipt_columns, ["barcode", "gtin", "ean"], "''")
    price_expr = _column_expr("rl", receipt_columns, ["parsed_price", "price"], "''")
    quantity_expr = _column_expr("rl", receipt_columns, ["parsed_quantity", "quantity"], "''")
    unit_expr = _column_expr("rl", receipt_columns, ["parsed_unit", "unit"], "''")
    matched_product_expr = _column_expr("rl", receipt_columns, ["matched_global_product_id", "global_product_id"], "''")
    created_expr = _column_expr("rl", receipt_columns, ["created_at"], "''")
    updated_expr = _column_expr("rl", receipt_columns, ["updated_at"], "''")

    join_sql = ""
    retailer_expr = "''"
    if receipts_exists and "receipt_id" in receipt_columns and "id" in receipts_columns:
        join_sql = "LEFT JOIN receipts r ON r.id = rl.receipt_id"
        retailer_expr = _column_expr("r", receipts_columns, ["store_name", "retailer_code", "store"], "''")

    rows = conn.execute(
        text(
            f"""
            SELECT
                {id_expr} AS receipt_line_id,
                '' AS purchase_import_line_id,
                {retailer_expr} AS retailer_code,
                COALESCE(NULLIF({text_expr}, ''), {raw_expr}) AS receipt_line_text,
                {barcode_expr} AS retailer_article_number,
                {barcode_expr} AS gtin,
                TRIM(COALESCE(CAST({quantity_expr} AS TEXT), '') || ' ' || COALESCE(CAST({unit_expr} AS TEXT), '')) AS quantity_label,
                {price_expr} AS price,
                {matched_product_expr} AS global_product_id,
                {created_expr} AS created_at,
                {updated_expr} AS updated_at
            FROM receipt_lines rl
            {join_sql}
            ORDER BY rl.id DESC
            LIMIT :limit
            """
        ),
        {"limit": max(1, min(int(limit or 200), 500))},
    ).mappings().all()

    placeholders: list[dict[str, Any]] = []
    for row in rows:
        item = _build_receipt_line_placeholder(dict(row))
        if not item.get("receipt_line_text"):
            continue
        if str(item.get("context_key") or "") in existing_context_keys:
            continue
        placeholders.append(item)

    return placeholders


def list_external_receipt_items(limit: int = 200) -> dict[str, Any]:
    ensure_external_product_candidates_schema()
    normalized_limit = max(1, min(int(limit or 200), 500))

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
        existing_context_keys = _candidate_context_keys(candidates)
        placeholders = _list_receipt_line_placeholders(conn, existing_context_keys, normalized_limit)

    # Bovenste tabel is bonartikelgedreven: purchase_import_lines-placeholders zijn leidend.
    # Candidates blijven detailregels onder dezelfde bonartikelcontext.
    combined = placeholders + candidates
    return {
        "items": combined[:normalized_limit],
        "candidate_rows": len(candidates),
        "receipt_line_rows": len(placeholders),
        "total": len(combined[:normalized_limit]),
    }


def unlink_external_catalog_links(
    context_keys: list[str] | None = None,
    candidate_ids: list[str] | None = None,
) -> dict[str, Any]:
    ensure_external_product_candidates_schema()

    normalized_context_keys = [str(value).strip() for value in (context_keys or []) if str(value).strip()]
    normalized_candidate_ids = [str(value).strip() for value in (candidate_ids or []) if str(value).strip()]

    if not normalized_context_keys and not normalized_candidate_ids:
        return {"ok": True, "unlinked_count": 0, "receipt_line_unlinked_count": 0}

    where_parts: list[str] = []
    params: dict[str, Any] = {}

    if normalized_context_keys:
        context_placeholders = []
        for index, value in enumerate(normalized_context_keys):
            key = f"context_key_{index}"
            context_placeholders.append(f":{key}")
            params[key] = value
        where_parts.append(f"context_key IN ({', '.join(context_placeholders)})")

    if normalized_candidate_ids:
        id_placeholders = []
        for index, value in enumerate(normalized_candidate_ids):
            key = f"candidate_id_{index}"
            id_placeholders.append(f":{key}")
            params[key] = value
        where_parts.append(f"id IN ({', '.join(id_placeholders)})")

    where_sql = " OR ".join(where_parts)

    with engine.begin() as conn:
        matched_rows = conn.execute(
            text(
                f"""
                SELECT id, receipt_line_id
                FROM external_product_candidates
                WHERE {where_sql}
                  AND (
                    global_product_id IS NOT NULL
                    OR status = 'linked_to_catalog'
                    OR candidate_status = 'linked_to_catalog'
                  )
                """
            ),
            params,
        ).mappings().all()

        conn.execute(
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

        receipt_line_ids = [
            str(row.get("receipt_line_id") or "").strip()
            for row in matched_rows
            if str(row.get("receipt_line_id") or "").strip()
        ]
        receipt_line_unlinked_count = 0

        if receipt_line_ids and _table_exists(conn, "receipt_lines"):
            receipt_columns = _table_columns(conn, "receipt_lines")
            if "matched_global_product_id" in receipt_columns:
                placeholders = []
                receipt_params: dict[str, Any] = {}
                for index, value in enumerate(receipt_line_ids):
                    key = f"receipt_line_id_{index}"
                    placeholders.append(f":{key}")
                    receipt_params[key] = value
                result = conn.execute(
                    text(
                        f"""
                        UPDATE receipt_lines
                        SET matched_global_product_id = NULL
                        WHERE id IN ({', '.join(placeholders)})
                        """
                    ),
                    receipt_params,
                )
                receipt_line_unlinked_count = int(result.rowcount or 0)

    return {
        "ok": True,
        "unlinked_count": len(matched_rows),
        "receipt_line_unlinked_count": receipt_line_unlinked_count,
        "candidate_ids": [str(row.get("id") or "") for row in matched_rows],
    }


# M2C2h-5 purchase_import_lines override

def _m2c2h5_table_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
    return {str(row.get("name") or "") for row in rows}


def _m2c2h5_table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
        {"table_name": table_name},
    ).first()
    return row is not None


def _m2c2h5_col(alias: str, columns: set[str], names: list[str], fallback: str = "''") -> str:
    for name in names:
        if name in columns:
            return f"{alias}.{name}"
    return fallback


def _m2c2i_fix7a3_retailer_from_purchase_import(row: dict[str, Any]) -> str:
    """Bepaal winkelketen voor een importregel uit de canonieke batchmetadata."""
    raw_payload = row.get("batch_raw_payload")

    if raw_payload:
        try:
            payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
        except Exception:
            payload = {}

        if isinstance(payload, dict):
            metadata = payload.get("batch_metadata") if isinstance(payload.get("batch_metadata"), dict) else {}
            for value in (
                metadata.get("store_name"),
                metadata.get("store_label"),
                payload.get("store_name"),
                payload.get("store_label"),
                payload.get("retailer_code"),
                payload.get("retailer"),
            ):
                normalized = str(value or "").strip()
                if normalized:
                    return normalized

    for value in (
        row.get("retailer_code"),
        row.get("store_name"),
        row.get("store_label"),
        row.get("brand_raw"),
    ):
        normalized = str(value or "").strip()
        if normalized and normalized.lower() not in {"-", "import", "onbekend", "unknown"}:
            return normalized

    return "onbekend"

def _m2c2h5_purchase_import_placeholder(row: dict[str, Any]) -> dict[str, Any]:
    purchase_import_line_id = str(row.get("purchase_import_line_id") or "").strip()
    article_name = str(row.get("article_name_raw") or "").strip()
    context_key = build_candidate_context_key(
        "import",
        article_name or purchase_import_line_id,
        purchase_import_line_id=purchase_import_line_id or None,
    )
    global_product_id = str(row.get("global_product_id") or "").strip()

    receipt_item_id = f"purchase-import-line:{purchase_import_line_id}" if purchase_import_line_id else ""
    return {
        "id": receipt_item_id,
        "receipt_item_id": receipt_item_id,
        "receipt_item_type": "purchase_import_line",
        "receipt_item_source_id": purchase_import_line_id or None,
        "receipt_line_id": None,
        "purchase_import_line_id": purchase_import_line_id or None,
        "context_key": context_key,
        "retailer_code": _m2c2i_fix7a3_retailer_from_purchase_import(row),
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


def _m2c2h5_list_purchase_import_placeholders(conn, existing_context_keys: set[str], limit: int) -> list[dict[str, Any]]:
    if not _m2c2h5_table_exists(conn, "purchase_import_lines"):
        return []

    columns = _m2c2h5_table_columns(conn, "purchase_import_lines")

    batch_join_sql = ""
    batch_raw_payload_expr = "''"
    if "batch_id" in columns and _m2c2h5_table_exists(conn, "purchase_import_batches"):
        batch_columns = _m2c2h5_table_columns(conn, "purchase_import_batches")
        if "id" in batch_columns:
            batch_join_sql = "LEFT JOIN purchase_import_batches pib ON pib.id = pil.batch_id"
            batch_raw_payload_expr = _m2c2h5_col("pib", batch_columns, ["raw_payload"], "''")
    id_expr = _m2c2h5_col("pil", columns, ["id"])
    code_expr = _m2c2h5_col("pil", columns, ["external_article_code"])
    name_expr = _m2c2h5_col("pil", columns, ["article_name_raw"])
    brand_expr = _m2c2h5_col("pil", columns, ["brand_raw"])
    quantity_expr = _m2c2h5_col("pil", columns, ["quantity_raw"])
    unit_expr = _m2c2h5_col("pil", columns, ["unit_raw"])
    price_expr = _m2c2h5_col("pil", columns, ["line_price_raw"])
    global_product_expr = _m2c2h5_col("pil", columns, ["matched_global_product_id", "matched_global_article_id"])
    created_expr = _m2c2h5_col("pil", columns, ["created_at"])
    updated_expr = _m2c2h5_col("pil", columns, ["updated_at"])

    rows = conn.execute(
        text(
            f"""
            SELECT
                {id_expr} AS purchase_import_line_id,
                {batch_raw_payload_expr} AS batch_raw_payload,
                {code_expr} AS external_article_code,
                {name_expr} AS article_name_raw,
                {brand_expr} AS brand_raw,
                {quantity_expr} AS quantity_raw,
                {unit_expr} AS unit_raw,
                {price_expr} AS line_price_raw,
                {global_product_expr} AS global_product_id,
                {created_expr} AS created_at,
                {updated_expr} AS updated_at
            FROM purchase_import_lines pil
            {batch_join_sql}
            ORDER BY pil.ui_sort_order ASC, pil.created_at DESC, pil.id DESC
            LIMIT :limit
            """
        ),
        {"limit": max(1, min(int(limit or 500), 500))},
    ).mappings().all()

    placeholders = []
    for row in rows:
        item = _m2c2h5_purchase_import_placeholder(dict(row))
        if not item.get("receipt_line_text"):
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
        candidates = _m2c2i_fix7b_ensure_catalog_products_for_article_codes(conn, candidates)
        existing_context_keys = {
            str(row.get("context_key") or "").strip()
            for row in candidates
            if str(row.get("context_key") or "").strip()
        }
        placeholders = _m2c2h5_list_purchase_import_placeholders(conn, existing_context_keys, normalized_limit)
        placeholders = _m2c2i_fix7a3_apply_catalog_status_to_placeholders(placeholders, candidates)

    # Bovenste tabel is bonartikelgedreven: purchase_import_lines-placeholders zijn leidend.
    # Candidates blijven detailregels onder dezelfde bonartikelcontext.
    combined = _m2c2i_fix7b_dedupe_top_receipt_items(placeholders)
    return {
        "items": combined[:normalized_limit],
        "candidate_rows": len(candidates),
        "purchase_import_line_rows": len(placeholders),
        "total": len(combined[:normalized_limit]),
    }


def _m2c2i_fix7a3_normalized_receipt_key(retailer_code: Any, receipt_line_text: Any) -> str:
    retailer = str(retailer_code or "").strip().lower()
    text_value = str(receipt_line_text or "").strip().lower()
    text_value = text_value.replace(".", "")
    text_value = " ".join(text_value.split())
    return f"{retailer}|{text_value}"


def _m2c2i_fix7a3_best_catalog_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    priority = {
        "linked_to_catalog": 3,
        "unlinked_from_catalog": 2,
    }

    best: dict[str, Any] | None = None
    best_score = 0

    for candidate in candidates:
        status = str(candidate.get("status") or candidate.get("candidate_status") or "").strip()
        score = priority.get(status, 0)
        if score > best_score:
            best = candidate
            best_score = score

    return best


def _m2c2i_fix7b_catalog_source_code(candidate: dict[str, Any]) -> str:
    return (
        str(candidate.get("retailer_article_number") or "").strip()
        or str(candidate.get("candidate_source_product_code") or "").strip()
        or str(candidate.get("source_product_code") or "").strip()
    )


def _m2c2i_fix7b_best_candidate_name(candidate: dict[str, Any]) -> str:
    return (
        str(candidate.get("candidate_name") or "").strip()
        or str(candidate.get("receipt_line_text") or "").strip()
        or "Onbekend product"
    )


def _m2c2i_fix7b_best_candidate_brand(candidate: dict[str, Any]) -> str:
    return (
        str(candidate.get("candidate_brand") or "").strip()
        or str(candidate.get("retailer_code") or "").strip()
        or None
    )


def _m2c2i_fix7b_candidate_is_confirmed_catalog_link(candidate: dict[str, Any]) -> bool:
    status_values = {
        str(candidate.get("status") or "").strip().lower(),
        str(candidate.get("candidate_status") or "").strip().lower(),
    }
    return bool(
        "linked_to_catalog" in status_values
        or "user_confirmed" in status_values
        or bool(candidate.get("is_user_confirmed"))
        or bool(candidate.get("is_external_database_override"))
    )


def _m2c2i_fix7b_identity_value(candidate: dict[str, Any]) -> str:
    source_code = _m2c2i_fix7b_catalog_source_code(candidate)
    retailer_code = str(candidate.get("retailer_code") or "").strip().lower()
    source_name = str(candidate.get("candidate_source_name") or candidate.get("source_name") or "external_product_candidate").strip().lower()
    if retailer_code and source_code:
        return f"retailer:{retailer_code}:{source_code}"
    if source_name and source_code:
        return f"source:{source_name}:{source_code}"
    return source_code


def _m2c2i_fix7b_catalog_lookup_values(candidate: dict[str, Any]) -> list[str]:
    values = []
    source_code = _m2c2i_fix7b_catalog_source_code(candidate)
    retailer_code = str(candidate.get("retailer_code") or "").strip().lower()
    source_name = str(candidate.get("candidate_source_name") or candidate.get("source_name") or "external_product_candidate").strip().lower()
    if retailer_code and source_code:
        values.append(f"retailer:{retailer_code}:{source_code}")
    if source_name and retailer_code and source_code:
        values.append(f"{source_name}:{retailer_code}:{source_code}")
    if source_name and source_code:
        values.append(f"source:{source_name}:{source_code}")
    if source_code:
        values.append(source_code)
    return list(dict.fromkeys(values))


def _m2c2i_fix7b_create_or_reuse_catalog_product_for_candidate(conn, candidate: dict[str, Any]) -> str:
    """Maak of hergebruik een global_product voor een bevestigde externe kandidaat.

    Dit maakt nadrukkelijk geen household_article en geen voorraadmutatie.
    """
    if not _m2c2h5_table_exists(conn, "global_products") or not _m2c2h5_table_exists(conn, "product_identities"):
        return str(candidate.get("global_product_id") or "").strip()

    source_code = _m2c2i_fix7b_catalog_source_code(candidate)
    if not source_code:
        return str(candidate.get("global_product_id") or "").strip()

    global_product_id = str(candidate.get("global_product_id") or "").strip()
    lookup_values = _m2c2i_fix7b_catalog_lookup_values(candidate)

    if not global_product_id and lookup_values:
        placeholders = []
        params: dict[str, Any] = {}
        for index, value in enumerate(lookup_values):
            key = f"identity_value_{index}"
            placeholders.append(f":{key}")
            params[key] = value

        existing = conn.execute(
            text(
                f"""
                SELECT global_product_id
                FROM product_identities
                WHERE identity_type = 'retailer_article_number'
                  AND identity_value IN ({', '.join(placeholders)})
                  AND COALESCE(global_product_id, '') <> ''
                LIMIT 1
                """
            ),
            params,
        ).mappings().first()

        if existing and str(existing.get("global_product_id") or "").strip():
            global_product_id = str(existing.get("global_product_id") or "").strip()

    if not global_product_id:
        global_product_id = str(uuid.uuid4())
        conn.execute(
            text(
                """
                INSERT INTO global_products (
                    id, primary_gtin, name, brand, variant, category,
                    size_value, size_unit, source, status, created_at, updated_at
                )
                VALUES (
                    :id, NULL, :name, :brand, :variant, :category,
                    NULL, NULL, :source, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": global_product_id,
                "name": _m2c2i_fix7b_best_candidate_name(candidate),
                "brand": _m2c2i_fix7b_best_candidate_brand(candidate),
                "variant": str(candidate.get("variant") or "").strip() or None,
                "category": str(candidate.get("candidate_category") or candidate.get("variant") or "").strip() or None,
                "source": str(candidate.get("candidate_source_name") or candidate.get("source_name") or "external_product_candidate").strip(),
            },
        )

    primary_identity = _m2c2i_fix7b_identity_value(candidate)
    if primary_identity:
        conn.execute(
            text(
                """
                INSERT INTO product_identities (
                    id, household_article_id, identity_type, identity_value,
                    source, confidence_score, is_primary, created_at, updated_at, global_product_id
                )
                SELECT
                    :id, '', 'retailer_article_number', :identity_value,
                    :source, 1.0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :global_product_id
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM product_identities
                    WHERE identity_type = 'retailer_article_number'
                      AND identity_value = :identity_value
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "identity_value": primary_identity,
                "source": str(candidate.get("candidate_source_name") or candidate.get("source_name") or "external_product_candidate").strip(),
                "global_product_id": global_product_id,
            },
        )

    return global_product_id


def _m2c2i_fix7b_ensure_catalog_products_for_article_codes(conn, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Vul catalogusreferenties voor bevestigde externe kandidaten met artikelcode.

    Zwakke of gewone preview-kandidaten worden niet automatisch catalogusproduct. Daarmee
    voorkomen we dat false positives zoals PREI -> artikelcode 21175 in de catalogus belanden.
    """
    enriched: list[dict[str, Any]] = []

    for candidate in candidates:
        next_candidate = dict(candidate)
        source_code = _m2c2i_fix7b_catalog_source_code(next_candidate)
        if not source_code or not _m2c2i_fix7b_candidate_is_confirmed_catalog_link(next_candidate):
            enriched.append(next_candidate)
            continue

        global_product_id = _m2c2i_fix7b_create_or_reuse_catalog_product_for_candidate(conn, next_candidate)
        if global_product_id:
            conn.execute(
                text(
                    """
                    UPDATE external_product_candidates
                    SET global_product_id = :global_product_id,
                        status = 'linked_to_catalog',
                        candidate_status = 'linked_to_catalog',
                        is_user_confirmed = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :candidate_id
                    """
                ),
                {
                    "global_product_id": global_product_id,
                    "candidate_id": next_candidate.get("id"),
                },
            )
            next_candidate["global_product_id"] = global_product_id
            next_candidate["status"] = "linked_to_catalog"
            next_candidate["candidate_status"] = "linked_to_catalog"
            next_candidate["is_user_confirmed"] = 1

        enriched.append(next_candidate)

    return enriched

def _m2c2i_fix7b_dedupe_top_receipt_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Toon één bovenste tabelrij per winkelketen + genormaliseerde bonartikelnaam."""
    best_by_key: dict[str, dict[str, Any]] = {}

    status_priority = {
        "linked_to_catalog": 5,
        "unlinked_from_catalog": 4,
        "candidate": 3,
        "possible_candidate": 2,
        "no_candidate": 1,
    }

    for item in items:
        key = _m2c2i_fix7a3_normalized_receipt_key(
            item.get("retailer_code"),
            item.get("receipt_line_text"),
        )

        current = best_by_key.get(key)
        item_status = str(item.get("status") or item.get("candidate_status") or "").strip()
        item_score = (
            status_priority.get(item_status, 0),
            1 if str(item.get("global_product_id") or "").strip() else 0,
            1 if str(item.get("retailer_article_number") or "").strip() else 0,
            str(item.get("updated_at") or item.get("created_at") or ""),
        )

        if current is None:
            best_by_key[key] = item
            continue

        current_status = str(current.get("status") or current.get("candidate_status") or "").strip()
        current_score = (
            status_priority.get(current_status, 0),
            1 if str(current.get("global_product_id") or "").strip() else 0,
            1 if str(current.get("retailer_article_number") or "").strip() else 0,
            str(current.get("updated_at") or current.get("created_at") or ""),
        )

        if item_score > current_score:
            best_by_key[key] = item

    return list(best_by_key.values())


def _m2c2i_fix7c_same_retailer_for_projection(placeholder: dict[str, object], candidate: dict[str, object]) -> bool:
    """Alleen candidates van dezelfde retailer mogen op een bonartikelrij worden geprojecteerd."""
    placeholder_retailer = str(placeholder.get("retailer_code") or "").strip().lower()
    candidate_retailer = str(candidate.get("retailer_code") or "").strip().lower()

    if not placeholder_retailer or not candidate_retailer:
        return False

    return placeholder_retailer == candidate_retailer


def _m2c2i_fix7a3_apply_catalog_status_to_placeholders(
    placeholders: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Projecteer catalogusstatus en detailkandidaten op de bonartikelrij."""
    by_purchase_import_line_id: dict[str, list[dict[str, Any]]] = {}
    by_receipt_key: dict[str, list[dict[str, Any]]] = {}

    def candidate_priority(candidate: dict[str, Any]) -> tuple:
        status = str(candidate.get("status") or candidate.get("candidate_status") or "").strip().lower()
        return (
            0 if status == "linked_to_catalog" else 1,
            0 if bool(candidate.get("is_user_confirmed")) else 1,
            0 if str(candidate.get("global_product_id") or "").strip() else 1,
            -float(candidate.get("score") or 0),
            str(candidate.get("candidate_name") or ""),
        )

    def normalize_candidate_for_detail(candidate: dict[str, Any]) -> dict[str, Any]:
        next_candidate = dict(candidate)
        try:
            next_candidate = _m2c2i_fix7a_apply_identifier_contract(next_candidate)
        except Exception:
            pass
        status = str(next_candidate.get("status") or next_candidate.get("candidate_status") or "").strip().lower()
        has_catalog = _m2c2i_fix2_has_catalog_reference(next_candidate) if "_m2c2i_fix2_has_catalog_reference" in globals() else bool(next_candidate.get("global_product_id"))
        is_linked = bool(status == "linked_to_catalog" and has_catalog)
        next_candidate["is_linked_to_catalog"] = is_linked
        next_candidate["is_existing_link_for_receipt_item"] = is_linked
        next_candidate["is_linkable_to_catalog"] = bool(not is_linked and _m2c2i_fix7b_catalog_source_code(next_candidate))
        if is_linked:
            next_candidate["status"] = "linked_to_catalog"
            next_candidate["candidate_status"] = "linked_to_catalog"
        return next_candidate

    for candidate in candidates:
        purchase_import_line_id = str(candidate.get("purchase_import_line_id") or "").strip()
        if purchase_import_line_id and not purchase_import_line_id.startswith("preview:"):
            by_purchase_import_line_id.setdefault(purchase_import_line_id, []).append(candidate)

        key = _m2c2i_fix7a3_normalized_receipt_key(
            candidate.get("retailer_code"),
            candidate.get("receipt_line_text"),
        )
        if key and key != "|":
            by_receipt_key.setdefault(key, []).append(candidate)

    enriched: list[dict[str, Any]] = []
    for placeholder in placeholders:
        matching_candidates: list[dict[str, Any]] = []

        purchase_import_line_id = str(placeholder.get("purchase_import_line_id") or "").strip()
        if purchase_import_line_id:
            matching_candidates.extend(by_purchase_import_line_id.get(purchase_import_line_id, []))

        key = _m2c2i_fix7a3_normalized_receipt_key(
            placeholder.get("retailer_code"),
            placeholder.get("receipt_line_text"),
        )
        matching_candidates.extend(by_receipt_key.get(key, []))

        matching_candidates = [
            candidate
            for candidate in matching_candidates
            if _m2c2i_fix7c_same_retailer_for_projection(placeholder, candidate)
        ]

        # Ontdubbel detailkandidaten op kandidaatidentiteit.
        unique: dict[str, dict[str, Any]] = {}
        for candidate in matching_candidates:
            identity = "|".join([
                str(candidate.get("id") or ""),
                str(candidate.get("candidate_source_name") or candidate.get("source_name") or ""),
                str(candidate.get("candidate_source_product_code") or candidate.get("source_product_code") or candidate.get("retailer_article_number") or ""),
                str(candidate.get("variant") or ""),
                str(candidate.get("candidate_name") or ""),
            ])
            if identity not in unique or candidate_priority(candidate) < candidate_priority(unique[identity]):
                unique[identity] = candidate

        detail_candidates = sorted(unique.values(), key=candidate_priority)
        best = detail_candidates[0] if detail_candidates else None

        if best:
            status = str(best.get("status") or best.get("candidate_status") or "").strip().lower()
            has_catalog = bool(str(best.get("global_product_id") or "").strip())
            placeholder = dict(placeholder)
            placeholder["candidates"] = [normalize_candidate_for_detail(candidate) for candidate in detail_candidates[:20]]
            placeholder["candidate_count"] = len(detail_candidates)

            if status == "linked_to_catalog" and has_catalog:
                placeholder["status"] = "linked_to_catalog"
                placeholder["candidate_status"] = "linked_to_catalog"
                placeholder["global_product_id"] = str(best.get("global_product_id") or "").strip() or None
                placeholder["is_linked_to_catalog"] = True
                placeholder["is_existing_link_for_receipt_item"] = True
                placeholder["canonical_catalog_product_id"] = placeholder["global_product_id"]
                placeholder["retailer_article_number"] = (
                    str(best.get("retailer_article_number") or best.get("candidate_source_product_code") or best.get("source_product_code") or "").strip()
                    or placeholder.get("retailer_article_number")
                )
            elif status == "unlinked_from_catalog":
                placeholder["status"] = "unlinked_from_catalog"
                placeholder["candidate_status"] = "unlinked_from_catalog"
                placeholder["retailer_article_number"] = (
                    str(best.get("retailer_article_number") or best.get("candidate_source_product_code") or best.get("source_product_code") or "").strip()
                    or placeholder.get("retailer_article_number")
                )
            elif detail_candidates:
                placeholder["status"] = "candidate"
                placeholder["candidate_status"] = "candidate"
        else:
            placeholder = dict(placeholder)
            placeholder["candidates"] = []
            placeholder["candidate_count"] = 0

        enriched.append(placeholder)

    return enriched

def unlink_external_catalog_links(
    context_keys: list[str] | None = None,
    candidate_ids: list[str] | None = None,
) -> dict[str, Any]:
    ensure_external_product_candidates_schema()

    normalized_context_keys = [str(value).strip() for value in (context_keys or []) if str(value).strip()]
    normalized_candidate_ids = [str(value).strip() for value in (candidate_ids or []) if str(value).strip()]

    if not normalized_context_keys and not normalized_candidate_ids:
        return {"ok": True, "unlinked_count": 0, "purchase_import_line_unlinked_count": 0}

    with engine.begin() as conn:
        unlinked_count = 0
        purchase_import_line_ids: list[str] = []

        if normalized_context_keys or normalized_candidate_ids:
            where_parts = []
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

            purchase_import_line_ids.extend([
                str(row.get("purchase_import_line_id") or "").strip()
                for row in rows
                if str(row.get("purchase_import_line_id") or "").strip()
            ])

        for context_key in normalized_context_keys:
            if context_key.startswith("purchase-import-line:"):
                purchase_import_line_ids.append(context_key.replace("purchase-import-line:", "", 1).strip())

        purchase_import_line_ids = sorted({value for value in purchase_import_line_ids if value})
        purchase_import_line_unlinked_count = 0

        if purchase_import_line_ids and _m2c2h5_table_exists(conn, "purchase_import_lines"):
            columns = _m2c2h5_table_columns(conn, "purchase_import_lines")
            if "matched_global_product_id" in columns:
                keys = []
                params = {}
                for index, value in enumerate(purchase_import_line_ids):
                    key = f"purchase_import_line_id_{index}"
                    keys.append(f":{key}")
                    params[key] = value

                result = conn.execute(
                    text(
                        f"""
                        UPDATE purchase_import_lines
                        SET matched_global_product_id = NULL
                        WHERE id IN ({', '.join(keys)})
                        """
                    ),
                    params,
                )
                purchase_import_line_unlinked_count = int(result.rowcount or 0)

    return {
        "ok": True,
        "unlinked_count": unlinked_count,
        "purchase_import_line_unlinked_count": purchase_import_line_unlinked_count,
    }


# M2C2h-5 paginated candidate ensure support

def ensure_external_receipt_item_candidates(items: list[dict[str, Any]] | None = None, include_below_threshold: bool = True) -> dict[str, Any]:
    """Zoek, weeg en bewaar kandidaten voor de zichtbare reeks bonartikelen.

    Deze functie maakt geen global_products, geen Mijn artikel en geen voorraadmutaties.
    """
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
        if retailer_code in {"-", "import", "onbekend"}:
            retailer_code = ""
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
            errors.append({
                "receipt_line_text": receipt_line_text,
                "retailer_code": retailer_code,
                "reason": str(exc),
            })

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


# M2C2i-2a-fix2 explicit candidate status fields
_m2c2i_fix2_previous_list_external_receipt_items = list_external_receipt_items


def _m2c2i_fix2_truthy(value) -> bool:
    normalized = str(value if value is not None else "").strip().lower()
    return bool(normalized and normalized not in {"-", "0", "none", "null", "undefined", "false"})


def _m2c2i_fix2_context_key(row: dict) -> str:
    return str(
        row.get("context_key")
        or row.get("receipt_line_id")
        or row.get("purchase_import_line_id")
        or row.get("receipt_line_text")
        or ""
    )


def _m2c2i_fix2_is_candidate_placeholder(row: dict) -> bool:
    return bool(row.get("is_receipt_item_placeholder"))


def _m2c2i_fix2_has_catalog_reference(row: dict) -> bool:
    return any(
        _m2c2i_fix2_truthy(row.get(field))
        for field in (
            "global_product_id",
            "product_identity_id",
            "matched_global_product_id",
            "matched_global_article_id",
        )
    )


def _m2c2i_fix7a_first_truthy(row: dict, fields: tuple[str, ...]) -> str:
    for field in fields:
        value = str(row.get(field) if row.get(field) is not None else "").strip()
        if _m2c2i_fix2_truthy(value):
            return value
    return ""


def _m2c2i_fix7a_apply_identifier_contract(row: dict) -> dict:
    next_row = dict(row)

    next_row["candidate_id"] = _m2c2i_fix7a_first_truthy(next_row, ("id",))
    next_row["external_source_name"] = _m2c2i_fix7a_first_truthy(
        next_row,
        ("candidate_source_name", "source_name"),
    )
    next_row["external_source_product_code"] = _m2c2i_fix7a_first_truthy(
        next_row,
        ("candidate_source_product_code", "source_product_code", "retailer_article_number"),
    )
    next_row["gtin"] = _m2c2i_fix7a_first_truthy(
        next_row,
        ("gtin", "ean", "code"),
    )
    next_row["canonical_catalog_product_id"] = _m2c2i_fix7a_first_truthy(
        next_row,
        ("global_product_id", "matched_global_product_id", "matched_global_article_id", "product_identity_id"),
    )

    return next_row

# M2C2i-2a-fix2b external candidates are linkable
def _m2c2i_fix2_has_external_candidate_identity(row: dict) -> bool:
    return bool(
        _m2c2i_fix2_truthy(row.get("candidate_name"))
        and (
            _m2c2i_fix2_truthy(row.get("candidate_source_name"))
            or _m2c2i_fix2_truthy(row.get("source_name"))
        )
        and (
            _m2c2i_fix2_truthy(row.get("candidate_source_product_code"))
            or _m2c2i_fix2_truthy(row.get("source_product_code"))
            or _m2c2i_fix2_truthy(row.get("retailer_article_number"))
        )
    )


def _m2c2i_fix2_has_explicit_link_status(row: dict) -> bool:
    status_values = {
        str(row.get("candidate_status") or "").strip().lower(),
        str(row.get("status") or "").strip().lower(),
    }
    return bool(
        "linked_to_catalog" in status_values
        or "user_confirmed" in status_values
        or bool(row.get("is_user_confirmed"))
        or bool(row.get("is_external_database_override"))
    )


def _m2c2i_fix2_link_priority(row: dict, index: int) -> tuple:
    status = str(row.get("candidate_status") or row.get("status") or "").strip().lower()
    return (
        0 if bool(row.get("is_user_confirmed")) else 1,
        0 if bool(row.get("is_external_database_override")) else 1,
        0 if status == "linked_to_catalog" else 1,
        index,
    )


def _m2c2i_fix2_apply_status_fields(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[tuple[int, dict]]] = {}

    for index, row in enumerate(rows):
        groups.setdefault(_m2c2i_fix2_context_key(row), []).append((index, row))

    active_link_indices: set[int] = set()
    group_has_active_link: dict[str, bool] = {}

    for context_key, entries in groups.items():
        explicit_linked = [
            (index, row)
            for index, row in entries
            if _m2c2i_fix2_has_explicit_link_status(row)
            and _m2c2i_fix2_has_catalog_reference(row)
        ]

        if explicit_linked:
            explicit_linked.sort(key=lambda item: _m2c2i_fix2_link_priority(item[1], item[0]))
            active_index = explicit_linked[0][0]
            active_link_indices.add(active_index)
            group_has_active_link[context_key] = True
        else:
            group_has_active_link[context_key] = False

    enriched: list[dict] = []

    for index, row in enumerate(rows):
        context_key = _m2c2i_fix2_context_key(row)
        is_placeholder = _m2c2i_fix2_is_candidate_placeholder(row)
        has_catalog_reference = _m2c2i_fix2_has_catalog_reference(row)
        explicit_link_status = _m2c2i_fix2_has_explicit_link_status(row)
        is_linked = bool(index in active_link_indices or (is_placeholder and has_catalog_reference and explicit_link_status))

        is_linkable = bool(
            not is_placeholder
            and not is_linked
            and (
                group_has_active_link.get(context_key, False)
                or has_catalog_reference
                or _m2c2i_fix2_has_external_candidate_identity(row)
            )
        )

        next_row = _m2c2i_fix7a_apply_identifier_contract(dict(row))
        next_row["is_linked_to_catalog"] = bool(is_linked)
        next_row["is_existing_link_for_receipt_item"] = bool(is_linked)
        next_row["is_linkable_to_catalog"] = bool(is_linkable)

        if is_linked:
            next_row["candidate_status"] = "linked_to_catalog"
            next_row["status"] = "linked_to_catalog"
        elif str(next_row.get("candidate_status") or "").strip().lower() in {"linked_to_catalog", "user_confirmed"}:
            next_row["candidate_status"] = "candidate"
            next_row["status"] = "candidate"

        # Verrijk geneste detailkandidaten voor de frontend.
        nested_candidates = []
        for candidate in next_row.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            nested = _m2c2i_fix7a_apply_identifier_contract(dict(candidate))
            nested_status = str(nested.get("status") or nested.get("candidate_status") or "").strip().lower()
            nested_has_catalog = _m2c2i_fix2_has_catalog_reference(nested)
            nested_is_linked = bool(nested_status == "linked_to_catalog" and nested_has_catalog)
            nested["is_linked_to_catalog"] = nested_is_linked
            nested["is_existing_link_for_receipt_item"] = nested_is_linked
            nested["is_linkable_to_catalog"] = bool(not nested_is_linked and _m2c2i_fix2_has_external_candidate_identity(nested))
            if nested_is_linked:
                nested["candidate_status"] = "linked_to_catalog"
                nested["status"] = "linked_to_catalog"
            nested_candidates.append(nested)
        next_row["candidates"] = nested_candidates

        enriched.append(next_row)

    return enriched

def list_external_receipt_items(limit: int = 500):
    payload = _m2c2i_fix2_previous_list_external_receipt_items(limit=limit)

    if isinstance(payload, dict):
        rows = payload.get("items") or []
        next_payload = dict(payload)
        enriched_rows = _m2c2i_fix2_apply_status_fields([
            dict(row) if hasattr(row, "items") else row
            for row in rows
        ])
        next_payload["items"] = _m2c2i_fix7b_dedupe_top_receipt_items(enriched_rows)
        next_payload["total"] = len(next_payload["items"])
        return next_payload

    rows = payload or []
    return _m2c2i_fix2_apply_status_fields([
        dict(row) if hasattr(row, "items") else row
        for row in rows
    ])


# M2C2i-2a-fix4 promote selected external candidate
def promote_external_product_candidate(candidate_id: str, force_overwrite: bool = False) -> dict:
    from sqlalchemy import text as sql_text
    from app.db import engine

    normalized_candidate_id = str(candidate_id or "").strip()
    if not normalized_candidate_id:
        return {"ok": False, "promoted": False, "reason": "missing_candidate_id"}

    with engine.begin() as conn:
        candidate = conn.execute(
            sql_text(
                """
                SELECT *
                FROM external_product_candidates
                WHERE id = :candidate_id
                LIMIT 1
                """
            ),
            {"candidate_id": normalized_candidate_id},
        ).mappings().first()

        if not candidate:
            return {"ok": False, "promoted": False, "reason": "candidate_not_found"}

        candidate_dict = dict(candidate)
        context_key = str(candidate_dict.get("context_key") or "").strip()

        if not context_key:
            return {"ok": False, "promoted": False, "reason": "missing_context_key"}

        linked_rows = conn.execute(
            sql_text(
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

        global_product_id = _m2c2i_fix7b_create_or_reuse_catalog_product_for_candidate(conn, candidate_dict)

        # Maak binnen dit bonartikel exact één actieve koppeling.
        conn.execute(
            sql_text(
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
            sql_text(
                """
                UPDATE external_product_candidates
                SET candidate_status = 'linked_to_catalog',
                    status = 'linked_to_catalog',
                    global_product_id = :global_product_id,
                    is_user_confirmed = 1,
                    is_external_database_override = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :candidate_id
                """
            ),
            {"candidate_id": normalized_candidate_id, "global_product_id": global_product_id or None},
        )

    return {
        "ok": True,
        "promoted": True,
        "requires_overwrite": False,
        "candidate_id": normalized_candidate_id,
        "context_key": context_key,
    }
