from __future__ import annotations

from typing import Any

from app.services.product_type_almost_out_decision_service import build_product_type_almost_out_decision
from app.services.product_type_forecast_service import build_product_type_forecast
from app.services.product_type_inventory_projection_service import build_product_type_inventory_projection
from app.services.product_type_purchase_need_service import build_product_type_purchase_needs
from app.services.product_type_quantity_event_service import aggregate_product_type_quantity_events


def _count(items: Any) -> int:
    return len(items) if isinstance(items, list) else 0


def build_product_type_readiness_audit(household_id: str) -> dict[str, Any]:
    """Controleer of de volledige Producttypeketen technisch bruikbaar en datadekkend is."""
    projection = build_product_type_inventory_projection(household_id)
    decision = build_product_type_almost_out_decision(household_id)
    purchase_needs = build_product_type_purchase_needs(household_id)
    history = aggregate_product_type_quantity_events(household_id)
    forecast = build_product_type_forecast(household_id)

    checks = [
        {
            "key": "inventory_projection_contract",
            "ok": projection.get("basis") == "product_type"
            and projection.get("read_only") is True
            and projection.get("mutates_inventory") is False,
        },
        {
            "key": "almost_out_decision_contract",
            "ok": decision.get("basis") == "product_type"
            and decision.get("article_policy_fallback") is False
            and decision.get("mutates_inventory") is False,
        },
        {
            "key": "purchase_need_contract",
            "ok": purchase_needs.get("basis") == "product_type"
            and purchase_needs.get("article_policy_fallback") is False
            and purchase_needs.get("concrete_article_selection_deferred") is True
            and purchase_needs.get("mutates_inventory") is False
            and purchase_needs.get("mutates_purchase_list") is False,
        },
        {
            "key": "history_snapshot_contract",
            "ok": history.get("basis") == "product_type_snapshot"
            and history.get("historical_membership_recalculated") is False
            and history.get("read_only") is True,
        },
        {
            "key": "forecast_contract",
            "ok": forecast.get("basis") == "product_type_snapshot"
            and forecast.get("history_source") == "product_type_quantity_events"
            and forecast.get("inventory_source") == "product_type_inventory_projection"
            and forecast.get("historical_membership_recalculated") is False
            and forecast.get("article_policy_fallback") is False
            and forecast.get("read_only") is True
            and forecast.get("mutates_inventory") is False,
        },
    ]

    source_rows = int(projection.get("source_inventory_rows") or 0)
    projected_rows = int(projection.get("projected_inventory_rows") or 0)
    excluded_rows = int(projection.get("excluded_inventory_rows") or 0)
    coverage_ratio = (projected_rows / source_rows) if source_rows else 1.0

    blockers: list[dict[str, Any]] = []
    if excluded_rows:
        blockers.append({
            "key": "inventory_projection_incomplete",
            "count": excluded_rows,
            "details": projection.get("exceptions") or [],
        })
    if not decision.get("items"):
        blockers.append({"key": "no_active_product_type_settings", "count": 0})
    if not history.get("items"):
        blockers.append({"key": "no_product_type_history", "count": 0})

    contract_green = all(bool(check.get("ok")) for check in checks)
    operationally_ready = contract_green and not blockers

    return {
        "household_id": str(household_id),
        "basis": "product_type_end_to_end",
        "read_only": True,
        "mutates_inventory": False,
        "mutates_purchase_list": False,
        "contract_green": contract_green,
        "operationally_ready": operationally_ready,
        "checks": checks,
        "coverage": {
            "source_inventory_rows": source_rows,
            "projected_inventory_rows": projected_rows,
            "excluded_inventory_rows": excluded_rows,
            "coverage_ratio": coverage_ratio,
            "product_types": int(projection.get("product_types") or 0),
            "almost_out_decisions": _count(decision.get("items")),
            "purchase_needs": _count(purchase_needs.get("items")),
            "history_product_types": _count(history.get("items")),
            "forecast_product_types": _count(forecast.get("items")),
        },
        "blockers": blockers,
    }
