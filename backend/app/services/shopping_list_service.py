from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
import uuid

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

ALLOWED_UNITS = {"", "stuk", "stuks", "gram", "kilogram", "milliliter", "liter", "verpakking"}
ALLOWED_SEARCH_SCOPES = {"household_articles", "product_types", "article_groups"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_columns(conn: Connection, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column.get("name") or "") for column in inspector.get_columns(table_name)}


def _ensure_column(conn: Connection, table_name: str, column_name: str, declaration: str) -> None:
    if column_name not in _table_columns(conn, table_name):
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}"))


def ensure_shopping_list_schema(conn: Connection) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS shopping_lists (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'completed')),
            created_at TEXT NOT NULL,
            completed_at TEXT,
            completed_by TEXT
        )
    """))
    conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_shopping_lists_household_active
        ON shopping_lists(household_id)
        WHERE status = 'active'
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS shopping_list_items (
            id TEXT PRIMARY KEY,
            shopping_list_id TEXT NOT NULL,
            household_id TEXT NOT NULL,
            article_name TEXT NOT NULL,
            article_group_name TEXT,
            product_type_name TEXT,
            source_type TEXT NOT NULL DEFAULT 'manual',
            source_id TEXT,
            quantity NUMERIC,
            volume NUMERIC,
            unit TEXT,
            size TEXT,
            note TEXT,
            checked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(shopping_list_id) REFERENCES shopping_lists(id)
        )
    """))
    _ensure_column(conn, "shopping_list_items", "article_group_name", "TEXT")
    _ensure_column(conn, "shopping_list_items", "product_type_name", "TEXT")
    _ensure_column(conn, "shopping_list_items", "source_id", "TEXT")
    _ensure_column(conn, "shopping_list_items", "size", "TEXT")
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_shopping_list_items_active
        ON shopping_list_items(household_id, shopping_list_id, checked, article_name)
    """))


def _normalize_decimal(value: Any, field_name: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} moet een geldig getal zijn") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} mag niet negatief zijn")
    return parsed


def _database_number(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _normalize_unit(value: Any) -> str:
    unit = str(value or "").strip().lower()
    if unit not in ALLOWED_UNITS:
        raise ValueError("Ongeldige eenheid")
    return unit


def _serialize_decimal(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _serialize_item(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "shopping_list_id": str(row.get("shopping_list_id") or ""),
        "household_id": str(row.get("household_id") or ""),
        "article_name": str(row.get("article_name") or ""),
        "article_group_name": str(row.get("article_group_name") or ""),
        "product_type_name": str(row.get("product_type_name") or ""),
        "source_type": str(row.get("source_type") or "manual"),
        "source_id": str(row.get("source_id") or ""),
        "quantity": _serialize_decimal(row.get("quantity")),
        "volume": _serialize_decimal(row.get("volume")),
        "unit": str(row.get("unit") or ""),
        "size": str(row.get("size") or ""),
        "note": str(row.get("note") or ""),
        "checked": bool(row.get("checked")),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _first_column(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _search_simple_table(
    conn: Connection,
    *,
    table_name: str,
    query: str,
    household_id: str | None,
    source_type: str,
    label_candidates: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    columns = _table_columns(conn, table_name)
    if not columns:
        return []
    id_column = _first_column(columns, ("id", "key", "code", "product_type_id", "inventory_group_key"))
    label_column = _first_column(columns, label_candidates)
    if not id_column or not label_column:
        return []
    household_clause = ""
    parameters: dict[str, Any] = {"query": f"%{query.lower()}%", "limit": limit}
    if household_id is not None and "household_id" in columns:
        household_clause = "AND household_id = :household_id"
        parameters["household_id"] = household_id
    rows = conn.execute(text(f"""
        SELECT {id_column} AS source_id, {label_column} AS label
        FROM {table_name}
        WHERE lower(trim(COALESCE({label_column}, ''))) LIKE :query
          {household_clause}
        ORDER BY lower(trim(COALESCE({label_column}, '')))
        LIMIT :limit
    """), parameters).mappings().all()
    return [
        {
            "source_type": source_type,
            "source_id": str(row.get("source_id") or ""),
            "label": str(row.get("label") or "").strip(),
            "article_name": str(row.get("label") or "").strip(),
            "article_group_name": str(row.get("label") or "").strip() if source_type == "article_group" else "",
            "product_type_name": str(row.get("label") or "").strip() if source_type == "product_type" else "",
        }
        for row in rows if str(row.get("label") or "").strip()
    ]


def search_shopping_catalog(
    conn: Connection,
    household_id: str,
    *,
    scope: str,
    query: str,
    limit: int = 20,
) -> dict[str, Any]:
    normalized_scope = str(scope or "").strip().lower()
    normalized_query = " ".join(str(query or "").strip().split())
    if normalized_scope not in ALLOWED_SEARCH_SCOPES:
        raise ValueError("Ongeldige zoekbron")
    if len(normalized_query) < 2:
        return {"scope": normalized_scope, "query": normalized_query, "items": [], "total": 0}
    safe_limit = max(1, min(int(limit or 20), 50))

    if normalized_scope == "article_groups":
        items = _search_simple_table(
            conn,
            table_name="article_groups",
            query=normalized_query,
            household_id=str(household_id),
            source_type="article_group",
            label_candidates=("name", "display_name", "article_group_name"),
            limit=safe_limit,
        )
    elif normalized_scope == "product_types":
        items = []
        for table_name in ("product_types", "global_product_types", "product_inventory_groups"):
            items.extend(_search_simple_table(
                conn,
                table_name=table_name,
                query=normalized_query,
                household_id=None,
                source_type="product_type",
                label_candidates=("name", "display_name", "product_type_name", "inventory_group_name"),
                limit=safe_limit,
            ))
            if items:
                break
    else:
        columns = _table_columns(conn, "household_articles")
        items = []
        if columns:
            id_column = _first_column(columns, ("id", "household_article_id"))
            label_column = _first_column(columns, ("article_name", "name", "display_name"))
            group_column = _first_column(columns, ("article_group_name", "group_name"))
            product_type_column = _first_column(columns, ("product_type_name", "type_name"))
            if id_column and label_column:
                rows = conn.execute(text(f"""
                    SELECT {id_column} AS source_id,
                           {label_column} AS label,
                           {group_column if group_column else 'NULL'} AS article_group_name,
                           {product_type_column if product_type_column else 'NULL'} AS product_type_name
                    FROM household_articles
                    WHERE household_id = :household_id
                      AND lower(trim(COALESCE({label_column}, ''))) LIKE :query
                    ORDER BY lower(trim(COALESCE({label_column}, '')))
                    LIMIT :limit
                """), {
                    "household_id": str(household_id),
                    "query": f"%{normalized_query.lower()}%",
                    "limit": safe_limit,
                }).mappings().all()
                items = [{
                    "source_type": "household_article",
                    "source_id": str(row.get("source_id") or ""),
                    "label": str(row.get("label") or "").strip(),
                    "article_name": str(row.get("label") or "").strip(),
                    "article_group_name": str(row.get("article_group_name") or ""),
                    "product_type_name": str(row.get("product_type_name") or ""),
                } for row in rows if str(row.get("label") or "").strip()]

    deduplicated: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("source_type") or ""), str(item.get("source_id") or item.get("label") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(item)
        if len(deduplicated) >= safe_limit:
            break
    return {"scope": normalized_scope, "query": normalized_query, "items": deduplicated, "total": len(deduplicated)}


def get_or_create_active_list(conn: Connection, household_id: str) -> dict[str, Any]:
    ensure_shopping_list_schema(conn)
    household_id = str(household_id or "").strip()
    if not household_id:
        raise ValueError("Huishouden ontbreekt")
    row = conn.execute(text("""
        SELECT id, household_id, status, created_at, completed_at, completed_by
        FROM shopping_lists
        WHERE household_id = :household_id AND status = 'active'
        LIMIT 1
    """), {"household_id": household_id}).mappings().first()
    if not row:
        list_id = str(uuid.uuid4())
        created_at = _utc_now_iso()
        conn.execute(text("""
            INSERT INTO shopping_lists(id, household_id, status, created_at)
            VALUES (:id, :household_id, 'active', :created_at)
        """), {"id": list_id, "household_id": household_id, "created_at": created_at})
        row = {"id": list_id, "household_id": household_id, "status": "active", "created_at": created_at, "completed_at": None, "completed_by": None}
    return dict(row)


def get_active_shopping_list(conn: Connection, household_id: str) -> dict[str, Any]:
    active = get_or_create_active_list(conn, household_id)
    rows = conn.execute(text("""
        SELECT id, shopping_list_id, household_id, article_name, article_group_name,
               product_type_name, source_type, source_id, quantity, volume, unit,
               size, note, checked, created_at, updated_at
        FROM shopping_list_items
        WHERE shopping_list_id = :shopping_list_id AND household_id = :household_id
        ORDER BY checked ASC, lower(article_name) ASC, created_at ASC
    """), {"shopping_list_id": active["id"], "household_id": str(household_id)}).mappings().all()
    return {**active, "items": [_serialize_item(row) for row in rows], "item_count": len(rows)}


def add_shopping_list_item(conn: Connection, household_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    active = get_or_create_active_list(conn, household_id)
    article_name = " ".join(str(payload.get("article_name") or payload.get("label") or "").strip().split())
    if not article_name:
        raise ValueError("Artikelnaam is verplicht")
    quantity = _database_number(_normalize_decimal(payload.get("quantity"), "Aantal"))
    volume = _database_number(_normalize_decimal(payload.get("volume"), "Volume"))
    unit = _normalize_unit(payload.get("unit"))
    item_id = str(uuid.uuid4())
    now = _utc_now_iso()
    values = {
        "id": item_id,
        "shopping_list_id": active["id"],
        "household_id": str(household_id),
        "article_name": article_name,
        "article_group_name": str(payload.get("article_group_name") or "").strip(),
        "product_type_name": str(payload.get("product_type_name") or "").strip(),
        "source_type": str(payload.get("source_type") or "manual").strip() or "manual",
        "source_id": str(payload.get("source_id") or "").strip(),
        "quantity": quantity,
        "volume": volume,
        "unit": unit,
        "size": str(payload.get("size") or "").strip(),
        "note": str(payload.get("note") or "").strip(),
        "created_at": now,
        "updated_at": now,
    }
    conn.execute(text("""
        INSERT INTO shopping_list_items(
            id, shopping_list_id, household_id, article_name, article_group_name,
            product_type_name, source_type, source_id, quantity, volume, unit,
            size, note, checked, created_at, updated_at
        ) VALUES (
            :id, :shopping_list_id, :household_id, :article_name, :article_group_name,
            :product_type_name, :source_type, :source_id, :quantity, :volume, :unit,
            :size, :note, 0, :created_at, :updated_at
        )
    """), values)
    row = conn.execute(text("SELECT * FROM shopping_list_items WHERE id = :id"), {"id": item_id}).mappings().one()
    return _serialize_item(row)


def update_shopping_list_item(conn: Connection, household_id: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    ensure_shopping_list_schema(conn)
    existing = conn.execute(text("SELECT * FROM shopping_list_items WHERE id = :id AND household_id = :household_id LIMIT 1"), {"id": str(item_id), "household_id": str(household_id)}).mappings().first()
    if not existing:
        return None
    article_name = " ".join(str(payload.get("article_name", existing["article_name"]) or "").strip().split())
    if not article_name:
        raise ValueError("Artikelnaam is verplicht")
    values = {
        "article_name": article_name,
        "article_group_name": str(payload.get("article_group_name", existing.get("article_group_name") or "") or "").strip(),
        "product_type_name": str(payload.get("product_type_name", existing.get("product_type_name") or "") or "").strip(),
        "quantity": _database_number(_normalize_decimal(payload.get("quantity", existing.get("quantity")), "Aantal")),
        "volume": _database_number(_normalize_decimal(payload.get("volume", existing.get("volume")), "Volume")),
        "unit": _normalize_unit(payload.get("unit", existing.get("unit"))),
        "size": str(payload.get("size", existing.get("size") or "") or "").strip(),
        "note": str(payload.get("note", existing.get("note") or "") or "").strip(),
        "checked": 1 if bool(payload.get("checked", bool(existing.get("checked")))) else 0,
        "updated_at": _utc_now_iso(),
        "id": str(item_id),
        "household_id": str(household_id),
    }
    conn.execute(text("""
        UPDATE shopping_list_items
        SET article_name = :article_name,
            article_group_name = :article_group_name,
            product_type_name = :product_type_name,
            quantity = :quantity,
            volume = :volume,
            unit = :unit,
            size = :size,
            note = :note,
            checked = :checked,
            updated_at = :updated_at
        WHERE id = :id AND household_id = :household_id
    """), values)
    row = conn.execute(text("SELECT * FROM shopping_list_items WHERE id = :id AND household_id = :household_id"), {"id": str(item_id), "household_id": str(household_id)}).mappings().one()
    return _serialize_item(row)


def delete_shopping_list_item(conn: Connection, household_id: str, item_id: str) -> bool:
    ensure_shopping_list_schema(conn)
    result = conn.execute(text("DELETE FROM shopping_list_items WHERE id = :id AND household_id = :household_id"), {"id": str(item_id), "household_id": str(household_id)})
    return bool(result.rowcount)


def complete_active_shopping_list(conn: Connection, household_id: str, completed_by: str) -> dict[str, Any]:
    active = get_or_create_active_list(conn, household_id)
    item_count = int(conn.execute(text("SELECT COUNT(*) FROM shopping_list_items WHERE shopping_list_id = :shopping_list_id AND household_id = :household_id"), {"shopping_list_id": active["id"], "household_id": str(household_id)}).scalar_one() or 0)
    completed_at = _utc_now_iso()
    conn.execute(text("""
        UPDATE shopping_lists
        SET status = 'completed', completed_at = :completed_at, completed_by = :completed_by
        WHERE id = :id AND household_id = :household_id AND status = 'active'
    """), {"completed_at": completed_at, "completed_by": str(completed_by or ""), "id": active["id"], "household_id": str(household_id)})
    next_active = get_or_create_active_list(conn, household_id)
    return {"status": "completed", "completed_list_id": active["id"], "completed_at": completed_at, "completed_item_count": item_count, "active_list_id": next_active["id"], "items": []}
