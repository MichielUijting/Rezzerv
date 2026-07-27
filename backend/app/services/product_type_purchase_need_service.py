from __future__ import annotations

from typing import Any

from app.services.product_type_almost_out_decision_service import (
    build_product_type_almost_out_decision,
)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_product_type_purchase_needs(household_id: str) -> dict[str, Any]:
    """Projecteer Bijna-op-beslissingen naar read-only inkoopbehoeften per Producttype.

    Een behoefte kiest nog geen concreet merk, GTIN, winkelartikel of verpakking.
    """
    decision = build_product_type_almost_out_decision(household_id)
    needs: list[dict[str, Any]] = []

    for item in decision.get("almost_out_items") or []:
        amount_to_buy = _number(item.get("amount_to_buy"))
        if amount_to_buy is None or amount_to_buy <= 0:
            continue
        needs.append({
            "product_type_id": item.get("product_type_id"),
            "product_type_name": item.get("product_type_name"),
            "required_quantity": amount_to_buy,
            "base_unit": item.get("base_unit") or "stuk",
            "current_quantity": _number(item.get("current_quantity")) or 0.0,
            "min_stock": _number(item.get("min_stock")),
            "ideal_stock": _number(item.get("ideal_stock")),
            "favorite_store": item.get("favorite_store"),
            "average_price": _number(item.get("average_price")),
            "preferred_packaging_unit": item.get("packaging_unit"),
            "preferred_packaging_quantity": _number(item.get("packaging_quantity")),
            "default_location_id": item.get("default_location_id"),
            "default_sublocation_id": item.get("default_sublocation_id"),
            "selection_state": "product_type_need_only",
            "concrete_article_selected": False,
            "global_product_id": None,
            "gtin": None,
            "household_article_id": None,
        })

    needs.sort(key=lambda item: (
        str(item.get("product_type_name") or "").lower(),
        str(item.get("product_type_id") or ""),
    ))

    return {
        "household_id": str(household_id),
        "basis": "product_type",
        "need_source": "product_type_almost_out_decision",
        "article_policy_fallback": False,
        "concrete_article_selection_deferred": True,
        "read_only": True,
        "mutates_inventory": False,
        "mutates_purchase_list": False,
        "items": needs,
        "count": len(needs),
        "projection_exceptions": decision.get("projection_exceptions") or [],
        "projection_summary": decision.get("projection_summary") or {},
    }
