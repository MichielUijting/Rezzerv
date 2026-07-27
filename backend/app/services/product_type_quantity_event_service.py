from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema
from app.services.product_type_resolution_service import resolve_product_type
from app.services.product_type_unit_conversion_service import convert_quantity

EVENT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS product_type_quantity_events (
    id TEXT PRIMARY KEY,
    household_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_at TEXT NOT NULL,
    household_article_id TEXT,
    global_product_id TEXT,
    product_type_id TEXT NOT NULL,
    product_type_name TEXT,
    source_quantity REAL NOT NULL,
    source_unit TEXT NOT NULL,
    base_quantity REAL NOT NULL,
    base_unit TEXT NOT NULL,
    conversion_source TEXT,
    source_reference TEXT,
    created_at TEXT NOT NULL
)
"""

EVENT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_product_type_quantity_events_household_type_date
ON product_type_quantity_events (household_id, product_type_id, event_at)
"""

ALLOWED_EVENT_TYPES = {"purchase", "consumption", "correction", "waste"}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_product_type_quantity_event_schema() -> None:
    ensure_product_inventory_group_schema()
    with engine.begin() as conn:
        conn.execute(text(EVENT_TABLE_SQL))
        conn.execute(text(EVENT_INDEX_SQL))


def record_product_type_quantity_event(
    *,
    household_id: str,
    event_type: str,
    source_quantity: float,
    source_unit: str,
    event_at: str | None = None,
    household_article_id: str | None = None,
    global_product_id: str | None = None,
    inventory_id: str | None = None,
    source_reference: str | None = None,
    conversion_source: str = "product_type_event_snapshot",
) -> dict[str, Any]:
    """Leg Producttype en omgerekende hoeveelheid als onveranderlijke eventsnapshot vast."""
    ensure_product_type_quantity_event_schema()
    household_id = _clean(household_id)
    event_type = _clean(event_type).lower()
    source_unit = _clean(source_unit)
    quantity = _number(source_quantity)
    if not household_id:
        raise ValueError("Huishouden ontbreekt")
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError("Onbekend Producttype-hoeveelheidsevent")
    if quantity is None or quantity < 0:
        raise ValueError("Hoeveelheid ontbreekt of is ongeldig")
    if not source_unit:
        raise ValueError("Broneenheid ontbreekt")

    resolution = resolve_product_type(
        household_article_id=household_article_id,
        global_product_id=global_product_id,
        inventory_id=inventory_id,
    )
    if resolution.get("status") != "resolved":
        return {
            "ok": False,
            "status": resolution.get("status"),
            "event_recorded": False,
            "resolution": resolution,
        }

    product_type = dict(resolution.get("product_type") or {})
    base_unit = _clean(product_type.get("base_unit")) or "stuk"
    base_quantity = convert_quantity(quantity, source_unit, base_unit)
    if base_quantity is None:
        return {
            "ok": False,
            "status": "missing_conversion",
            "event_recorded": False,
            "product_type": product_type,
            "source_quantity": quantity,
            "source_unit": source_unit,
            "base_unit": base_unit,
        }

    event_id = str(uuid.uuid4())
    params = {
        "id": event_id,
        "household_id": household_id,
        "event_type": event_type,
        "event_at": _clean(event_at) or _now_iso(),
        "household_article_id": _clean(household_article_id) or None,
        "global_product_id": _clean(global_product_id or resolution.get("global_product_id")) or None,
        "product_type_id": _clean(product_type.get("product_type_id")),
        "product_type_name": _clean(product_type.get("product_type_name")),
        "source_quantity": quantity,
        "source_unit": source_unit,
        "base_quantity": base_quantity,
        "base_unit": base_unit,
        "conversion_source": _clean(conversion_source),
        "source_reference": _clean(source_reference) or None,
        "created_at": _now_iso(),
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO product_type_quantity_events (
                    id, household_id, event_type, event_at,
                    household_article_id, global_product_id,
                    product_type_id, product_type_name,
                    source_quantity, source_unit,
                    base_quantity, base_unit,
                    conversion_source, source_reference, created_at
                ) VALUES (
                    :id, :household_id, :event_type, :event_at,
                    :household_article_id, :global_product_id,
                    :product_type_id, :product_type_name,
                    :source_quantity, :source_unit,
                    :base_quantity, :base_unit,
                    :conversion_source, :source_reference, :created_at
                )
                """
            ),
            params,
        )
    return {"ok": True, "status": "recorded", "event_recorded": True, "event": params}


def aggregate_product_type_quantity_events(household_id: str) -> dict[str, Any]:
    """Aggregeer historie per Producttype zonder koppelingen achteraf opnieuw te resolveren."""
    ensure_product_type_quantity_event_schema()
    household_id = _clean(household_id)
    if not household_id:
        raise ValueError("Huishouden ontbreekt")
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT product_type_id,
                       MAX(product_type_name) AS product_type_name,
                       base_unit,
                       SUM(CASE WHEN event_type = 'purchase' THEN base_quantity ELSE 0 END) AS purchased_quantity,
                       SUM(CASE WHEN event_type IN ('consumption', 'waste') THEN base_quantity ELSE 0 END) AS consumed_quantity,
                       SUM(CASE WHEN event_type = 'correction' THEN base_quantity ELSE 0 END) AS corrected_quantity,
                       COUNT(*) AS event_count,
                       MIN(event_at) AS first_event_at,
                       MAX(event_at) AS last_event_at
                FROM product_type_quantity_events
                WHERE household_id = :household_id
                GROUP BY product_type_id, base_unit
                ORDER BY lower(MAX(product_type_name)), product_type_id
                """
            ),
            {"household_id": household_id},
        ).mappings().all()
    return {
        "household_id": household_id,
        "basis": "product_type_snapshot",
        "historical_membership_recalculated": False,
        "read_only": True,
        "items": [dict(row) for row in rows],
    }
