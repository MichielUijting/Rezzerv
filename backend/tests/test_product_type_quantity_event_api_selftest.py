from __future__ import annotations

from app.api.product_inventory_group_routes import product_type_quantity_event_history


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    result = product_type_quantity_event_history("1")
    _assert(result.get("basis") == "product_type_snapshot", "historie-API gebruikt onjuiste basis")
    _assert(result.get("historical_membership_recalculated") is False, "historie mag koppelingen niet achteraf herberekenen")
    _assert(result.get("read_only") is True, "historie-API moet read-only zijn")
    _assert(isinstance(result.get("items"), list), "historie-items ontbreken")
    print("PASS product_type_quantity_event_api_contract")
    print("PRODUCT_TYPE_QUANTITY_EVENT_API_GREEN")


if __name__ == "__main__":
    main()
