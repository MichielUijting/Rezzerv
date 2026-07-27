from app.services.product_type_operational_action_service import (
    build_product_type_operational_actions,
)


result = build_product_type_operational_actions("1")

assert result["basis"] == "product_type_operational_readiness"
assert result["read_only"] is True
assert result["mutates_inventory"] is False
assert result["mutates_purchase_list"] is False
assert result["auto_executes_actions"] is False
print("PASS product_type_operational_action_contract")

assert result["contract_green"] is True
assert result["operationally_ready"] is False
assert result["required_action_count"] >= 1
print("PASS product_type_operational_action_readiness_split")

next_action = result["next_required_action"]
assert isinstance(next_action, dict)
assert next_action["key"] == "resolve_missing_global_products"
assert next_action["priority"] == 1
assert next_action["affected_count"] == 6
assert next_action["requires_user_confirmation"] is True
assert next_action["mutates_inventory"] is False
print("PASS product_type_operational_action_priority")

print("PRODUCT_TYPE_OPERATIONAL_ACTION_PHASE_J_GREEN")
