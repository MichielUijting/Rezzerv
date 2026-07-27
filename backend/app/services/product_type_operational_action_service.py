from __future__ import annotations

from typing import Any

from app.services.product_type_readiness_audit_service import (
    build_product_type_readiness_audit,
)


def build_product_type_operational_actions(household_id: str) -> dict[str, Any]:
    """Vertaal read-only gereedheidsblokkades naar concrete, niet-muterende vervolgstappen."""
    audit = build_product_type_readiness_audit(household_id)
    actions: list[dict[str, Any]] = []

    for blocker in audit.get("blockers") or []:
        key = str(blocker.get("key") or "")
        count = int(blocker.get("count") or 0)
        details = blocker.get("details") or []

        if key == "inventory_projection_incomplete":
            actions.append({
                "key": "resolve_missing_global_products",
                "priority": 1,
                "required": count > 0,
                "affected_count": count,
                "source_blocker": key,
                "target_state": "all_inventory_rows_have_resolved_product_type",
                "mutates_inventory": False,
                "requires_user_confirmation": True,
                "items": details,
            })
        elif key == "no_active_product_type_settings":
            actions.append({
                "key": "configure_product_type_thresholds",
                "priority": 2,
                "required": True,
                "affected_count": count,
                "source_blocker": key,
                "target_state": "active_minimum_and_ideal_stock_per_product_type",
                "mutates_inventory": False,
                "requires_user_confirmation": True,
                "items": [],
            })
        elif key == "no_product_type_history":
            actions.append({
                "key": "start_product_type_history_capture",
                "priority": 3,
                "required": True,
                "affected_count": count,
                "source_blocker": key,
                "target_state": "sufficient_product_type_consumption_history",
                "mutates_inventory": False,
                "requires_user_confirmation": False,
                "items": [],
            })

    actions.sort(key=lambda item: (int(item.get("priority") or 999), str(item.get("key") or "")))
    required_actions = [item for item in actions if item.get("required")]

    return {
        "household_id": str(household_id),
        "basis": "product_type_operational_readiness",
        "contract_green": bool(audit.get("contract_green")),
        "operationally_ready": bool(audit.get("operationally_ready")),
        "read_only": True,
        "mutates_inventory": False,
        "mutates_purchase_list": False,
        "auto_executes_actions": False,
        "actions": actions,
        "required_action_count": len(required_actions),
        "next_required_action": required_actions[0] if required_actions else None,
        "coverage": audit.get("coverage") or {},
    }
