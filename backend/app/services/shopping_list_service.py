from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

ALLOWED_UNITS = {"", "stuk", "stuks", "gram", "kilogram", "milliliter", "liter", "verpakking"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            quantity NUMERIC,
            volume NUMERIC,
            unit TEXT,
            note TEXT,
            checked INTEGER NOT NULL DEFAULT 0,
            source_type TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(shopping_list_id) REFERENCES shopping_lists(id)
        )
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_shopping_list_items_active
        ON shopping_list_items(household_id, shopping_list_id, checked, article_name)
    """))


def _normalize_decimal(value: Any, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} moet een geldig getal zijn") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} mag niet negatief zijn")
    return float(parsed)


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
        "quantity": _serialize_decimal(row.get("quantity")),
        "volume": _serialize_decimal(row.get("volume")),
        "unit": str(row.get("unit") or ""),
        "note": str(row.get("note") or ""),
        "checked": bool(row.get("checked")),
        "source_type": str(row.get("source_type") or "manual"),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


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
        row = {
            "id": list_id,
            "household_id": household_id,
            "status": "active",
            "created_at": created_at,
            "completed_at": None,
            "completed_by": None,
        }
    return dict(row)


def get_active_shopping_list(conn: Connection, household_id: str) -> dict[str, Any]:
    active = get_or_create_active_list(conn, household_id)
    rows = conn.execute(text("""
        SELECT id, shopping_list_id, household_id, article_name, quantity, volume,
               unit, note, checked, source_type, created_at, updated_at
        FROM shopping_list_items
        WHERE shopping_list_id = :shopping_list_id AND household_id = :household_id
        ORDER BY checked ASC, lower(article_name) ASC, created_at ASC
    """), {
        "shopping_list_id": active["id"],
        "household_id": str(household_id),
    }).mappings().all()
    return {
        **active,
        "items": [_serialize_item(row) for row in rows],
        "item_count": len(rows),
    }


def add_shopping_list_item(conn: Connection, household_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    active = get_or_create_active_list(conn, household_id)
    article_name = " ".join(str(payload.get("article_name") or "").strip().split())
    if not article_name:
        raise ValueError("Artikelnaam is verplicht")
    quantity = _normalize_decimal(payload.get("quantity"), "Aantal")
    volume = _normalize_decimal(payload.get("volume"), "Volume")
    unit = _normalize_unit(payload.get("unit"))
    note = str(payload.get("note") or "").strip()
    item_id = str(uuid.uuid4())
    now = _utc_now_iso()
    conn.execute(text("""
        INSERT INTO shopping_list_items(
            id, shopping_list_id, household_id, article_name, quantity, volume,
            unit, note, checked, source_type, created_at, updated_at
        ) VALUES (
            :id, :shopping_list_id, :household_id, :article_name, :quantity, :volume,
            :unit, :note, 0, 'manual', :created_at, :updated_at
        )
    """), {
        "id": item_id,
        "shopping_list_id": active["id"],
        "household_id": str(household_id),
        "article_name": article_name,
        "quantity": quantity,
        "volume": volume,
        "unit": unit,
        "note": note,
        "created_at": now,
        "updated_at": now,
    })
    row = conn.execute(text("""
        SELECT id, shopping_list_id, household_id, article_name, quantity, volume,
               unit, note, checked, source_type, created_at, updated_at
        FROM shopping_list_items WHERE id = :id
    """), {"id": item_id}).mappings().one()
    return _serialize_item(row)


def update_shopping_list_item(
    conn: Connection,
    household_id: str,
    item_id: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    ensure_shopping_list_schema(conn)
    existing = conn.execute(text("""
        SELECT id, article_name, quantity, volume, unit, note, checked
        FROM shopping_list_items
        WHERE id = :id AND household_id = :household_id
        LIMIT 1
    """), {"id": str(item_id), "household_id": str(household_id)}).mappings().first()
    if not existing:
        return None
    article_name = " ".join(str(payload.get("article_name", existing["article_name"]) or "").strip().split())
    if not article_name:
        raise ValueError("Artikelnaam is verplicht")
    quantity = _normalize_decimal(payload.get("quantity", existing.get("quantity")), "Aantal")
    volume = _normalize_decimal(payload.get("volume", existing.get("volume")), "Volume")
    unit = _normalize_unit(payload.get("unit", existing.get("unit")))
    note = str(payload.get("note", existing.get("note") or "") or "").strip()
    checked = bool(payload.get("checked", bool(existing.get("checked"))))
    conn.execute(text("""
        UPDATE shopping_list_items
        SET article_name = :article_name,
            quantity = :quantity,
            volume = :volume,
            unit = :unit,
            note = :note,
            checked = :checked,
            updated_at = :updated_at
        WHERE id = :id AND household_id = :household_id
    """), {
        "article_name": article_name,
        "quantity": quantity,
        "volume": volume,
        "unit": unit,
        "note": note,
        "checked": 1 if checked else 0,
        "updated_at": _utc_now_iso(),
        "id": str(item_id),
        "household_id": str(household_id),
    })
    row = conn.execute(text("""
        SELECT id, shopping_list_id, household_id, article_name, quantity, volume,
               unit, note, checked, source_type, created_at, updated_at
        FROM shopping_list_items WHERE id = :id AND household_id = :household_id
    """), {"id": str(item_id), "household_id": str(household_id)}).mappings().one()
    return _serialize_item(row)


def delete_shopping_list_item(conn: Connection, household_id: str, item_id: str) -> bool:
    ensure_shopping_list_schema(conn)
    result = conn.execute(text("""
        DELETE FROM shopping_list_items
        WHERE id = :id AND household_id = :household_id
    """), {"id": str(item_id), "household_id": str(household_id)})
    return bool(result.rowcount)


def complete_active_shopping_list(
    conn: Connection,
    household_id: str,
    completed_by: str,
) -> dict[str, Any]:
    active = get_or_create_active_list(conn, household_id)
    item_count = int(conn.execute(text("""
        SELECT COUNT(*) FROM shopping_list_items
        WHERE shopping_list_id = :shopping_list_id AND household_id = :household_id
    """), {
        "shopping_list_id": active["id"],
        "household_id": str(household_id),
    }).scalar_one() or 0)
    completed_at = _utc_now_iso()
    conn.execute(text("""
        UPDATE shopping_lists
        SET status = 'completed', completed_at = :completed_at, completed_by = :completed_by
        WHERE id = :id AND household_id = :household_id AND status = 'active'
    """), {
        "completed_at": completed_at,
        "completed_by": str(completed_by or ""),
        "id": active["id"],
        "household_id": str(household_id),
    })
    next_active = get_or_create_active_list(conn, household_id)
    return {
        "status": "completed",
        "completed_list_id": active["id"],
        "completed_at": completed_at,
        "completed_item_count": item_count,
        "active_list_id": next_active["id"],
        "items": [],
    }
