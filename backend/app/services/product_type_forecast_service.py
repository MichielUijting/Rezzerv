from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_type_inventory_projection_service import build_product_type_inventory_projection
from app.services.product_type_quantity_event_service import ensure_product_type_quantity_event_schema


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    raw = _clean(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_product_type_forecast(household_id: str) -> dict[str, Any]:
    """Bouw een eenvoudige verbruiksprognose uitsluitend uit Producttypesnapshots.

    De service herresolveert historische artikelen niet en gebruikt geen artikelgebonden
    beleidsinstellingen. Bij onvoldoende historie wordt expliciet geen prognose gemaakt.
    """
    ensure_product_type_quantity_event_schema()
    household_id = _clean(household_id)
    if not household_id:
        raise ValueError("Huishouden ontbreekt")

    projection = build_product_type_inventory_projection(household_id)
    projection_by_id = {
        str(item.get("product_type_id") or ""): dict(item)
        for item in projection.get("items") or []
        if str(item.get("product_type_id") or "")
    }

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT product_type_id,
                       MAX(product_type_name) AS product_type_name,
                       base_unit,
                       SUM(CASE WHEN event_type IN ('consumption', 'waste') THEN base_quantity ELSE 0 END) AS consumed_quantity,
                       COUNT(CASE WHEN event_type IN ('consumption', 'waste') THEN 1 END) AS consumption_event_count,
                       MIN(CASE WHEN event_type IN ('consumption', 'waste') THEN event_at END) AS first_consumption_at,
                       MAX(CASE WHEN event_type IN ('consumption', 'waste') THEN event_at END) AS last_consumption_at
                FROM product_type_quantity_events
                WHERE household_id = :household_id
                GROUP BY product_type_id, base_unit
                ORDER BY lower(MAX(product_type_name)), product_type_id
                """
            ),
            {"household_id": household_id},
        ).mappings().all()

    history_by_id = {str(row.get("product_type_id") or ""): dict(row) for row in rows}
    product_type_ids = sorted(set(projection_by_id) | set(history_by_id))
    items: list[dict[str, Any]] = []

    for product_type_id in product_type_ids:
        projected = projection_by_id.get(product_type_id) or {}
        history = history_by_id.get(product_type_id) or {}
        product_type_name = history.get("product_type_name") or projected.get("product_type_name") or product_type_id
        base_unit = history.get("base_unit") or projected.get("base_unit") or "stuk"
        current_quantity = _number(projected.get("current_quantity"))
        consumed_quantity = _number(history.get("consumed_quantity")) or 0.0
        event_count = int(history.get("consumption_event_count") or 0)
        first_at = _parse_datetime(history.get("first_consumption_at"))
        last_at = _parse_datetime(history.get("last_consumption_at"))

        elapsed_days = None
        average_daily_consumption = None
        days_until_depletion = None
        status = "insufficient_history"

        if event_count > 0 and first_at and last_at:
            elapsed_days = max(1.0, (last_at - first_at).total_seconds() / 86400.0)
            average_daily_consumption = consumed_quantity / elapsed_days if consumed_quantity > 0 else 0.0
            if current_quantity is None:
                status = "missing_current_inventory"
            elif average_daily_consumption > 0:
                days_until_depletion = current_quantity / average_daily_consumption
                status = "forecast_available"
            else:
                status = "no_consumption_rate"

        items.append({
            "product_type_id": product_type_id,
            "product_type_name": product_type_name,
            "base_unit": base_unit,
            "current_quantity": current_quantity,
            "consumed_quantity": consumed_quantity,
            "consumption_event_count": event_count,
            "history_span_days": elapsed_days,
            "average_daily_consumption": average_daily_consumption,
            "days_until_depletion": days_until_depletion,
            "status": status,
        })

    return {
        "household_id": household_id,
        "basis": "product_type_snapshot",
        "history_source": "product_type_quantity_events",
        "inventory_source": "product_type_inventory_projection",
        "historical_membership_recalculated": False,
        "article_policy_fallback": False,
        "read_only": True,
        "mutates_inventory": False,
        "items": items,
        "projection_exceptions": projection.get("exceptions") or [],
    }
