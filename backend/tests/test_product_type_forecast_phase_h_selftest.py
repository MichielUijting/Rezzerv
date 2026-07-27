from __future__ import annotations

from app.services.product_type_forecast_service import build_product_type_forecast


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    result = build_product_type_forecast("1")

    _assert(result.get("basis") == "product_type_snapshot", "prognosebasis is niet Producttypesnapshot")
    _assert(result.get("history_source") == "product_type_quantity_events", "onjuiste historiebron")
    _assert(result.get("inventory_source") == "product_type_inventory_projection", "onjuiste voorraadbron")
    _assert(result.get("historical_membership_recalculated") is False, "historische koppelingen mogen niet worden herberekend")
    _assert(result.get("article_policy_fallback") is False, "artikelgebonden fallback is niet toegestaan")
    _assert(result.get("read_only") is True, "prognose moet read-only zijn")
    _assert(result.get("mutates_inventory") is False, "prognose mag voorraad niet muteren")
    _assert(isinstance(result.get("items"), list), "prognose-items ontbreken")
    _assert(isinstance(result.get("projection_exceptions"), list), "projectie-uitzonderingen ontbreken")
    print("PASS product_type_forecast_sources")

    allowed_states = {
        "insufficient_history",
        "missing_current_inventory",
        "forecast_available",
        "no_consumption_rate",
    }
    for item in result.get("items") or []:
        _assert(item.get("status") in allowed_states, "onbekende prognosestatus")
        if item.get("status") == "forecast_available":
            _assert(item.get("average_daily_consumption") is not None, "verbruiksritme ontbreekt")
            _assert(item.get("days_until_depletion") is not None, "uitputtingsduur ontbreekt")
    print("PASS product_type_forecast_contract")

    print("PRODUCT_TYPE_FORECAST_PHASE_H_GREEN")


if __name__ == "__main__":
    main()
