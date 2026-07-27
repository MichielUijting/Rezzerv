from __future__ import annotations

from typing import Any

from app.services.product_type_household_settings_service import (
    list_extended_product_type_settings,
)
from app.services.product_type_inventory_projection_service import (
    build_product_type_inventory_projection,
)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_product_type_almost_out_decision(household_id: str) -> dict[str, Any]:
    """Combineer uitsluitend Producttype-instellingen met de read-only voorraadprojectie."""
    projection = build_product_type_inventory_projection(household_id)
    settings_payload = list_extended_product_type_settings(household_id)

    projection_by_id = {
        str(item.get("product_type_id") or ""): dict(item)
        for item in projection.get("items") or []
        if str(item.get("product_type_id") or "")
    }
    settings = [
        dict(item)
        for item in settings_payload.get("items") or []
        if bool(item.get("active", 1)) and bool(item.get("consumable", 1))
    ]

    items: list[dict[str, Any]] = []
    for setting in settings:
        product_type_id = str(setting.get("product_type_id") or "")
        projected = projection_by_id.get(product_type_id)
        minimum = _number(setting.get("min_stock"))
        ideal = _number(setting.get("ideal_stock"))

        if projected is None:
            current = 0.0
            data_state = "no_projected_inventory"
            reason = "no_projected_inventory"
            contributing_articles = 0
            contributing_inventory_rows = 0
            contributing_locations = 0
        else:
            current = float(projected.get("current_quantity") or 0.0)
            data_state = "ok"
            reason = "below_or_equal_minimum" if minimum is not None and current <= minimum else "above_minimum"
            contributing_articles = int(projected.get("contributing_articles") or 0)
            contributing_inventory_rows = int(projected.get("contributing_inventory_rows") or 0)
            contributing_locations = int(projected.get("contributing_locations") or 0)

        if minimum is None:
            include = False
            data_state = "missing_setting"
            reason = "missing_minimum"
        elif projected is None:
            include = False
        else:
            include = current <= minimum

        amount_to_buy = max(0.0, float(ideal) - current) if ideal is not None and projected is not None else 0.0

        items.append({
            "product_type_id": product_type_id,
            "product_type_name": setting.get("product_type_name") or product_type_id,
            "base_unit": setting.get("base_unit") or (projected or {}).get("base_unit") or "stuk",
            "aggregation_mode": setting.get("aggregation_mode") or (projected or {}).get("aggregation_mode") or "sum_quantity",
            "current_quantity": current,
            "min_stock": minimum,
            "ideal_stock": ideal,
            "amount_to_buy": amount_to_buy,
            "include_in_almost_out": include,
            "reason": reason,
            "data_state": data_state,
            "contributing_articles": contributing_articles,
            "contributing_inventory_rows": contributing_inventory_rows,
            "contributing_locations": contributing_locations,
            "favorite_store": setting.get("favorite_store"),
            "average_price": setting.get("average_price"),
            "auto_restock": bool(setting.get("auto_restock", 0)),
            "default_location_id": setting.get("default_location_id"),
            "default_sublocation_id": setting.get("default_sublocation_id"),
            "packaging_unit": setting.get("packaging_unit"),
            "packaging_quantity": setting.get("packaging_quantity"),
        })

    items.sort(key=lambda item: (str(item.get("product_type_name") or "").lower(), str(item.get("product_type_id") or "")))
    return {
        "household_id": str(household_id),
        "basis": "product_type",
        "policy_source": "household_product_type_settings",
        "inventory_source": "product_type_inventory_projection",
        "article_policy_fallback": False,
        "read_only": True,
        "mutates_inventory": False,
        "items": items,
        "almost_out_items": [item for item in items if item.get("include_in_almost_out")],
        "projection_exceptions": projection.get("exceptions") or [],
        "projection_summary": {
            "source_inventory_rows": projection.get("source_inventory_rows", 0),
            "projected_inventory_rows": projection.get("projected_inventory_rows", 0),
            "excluded_inventory_rows": projection.get("excluded_inventory_rows", 0),
            "product_types": projection.get("product_types", 0),
            "all_inventory_projected": projection.get("all_inventory_projected", False),
        },
    }
