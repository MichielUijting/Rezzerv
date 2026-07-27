from __future__ import annotations

from app.services.product_type_almost_out_decision_service import (
    build_product_type_almost_out_decision,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    result = build_product_type_almost_out_decision("1")
    _assert(result.get("basis") == "product_type", "Bijna op gebruikt niet Producttype als basis")
    _assert(result.get("policy_source") == "household_product_type_settings", "onjuiste beleidsbron")
    _assert(result.get("inventory_source") == "product_type_inventory_projection", "onjuiste voorraadbron")
    _assert(result.get("article_policy_fallback") is False, "artikelgebonden fallback is verboden")
    _assert(result.get("read_only") is True, "besliscontract moet read-only zijn")
    _assert(result.get("mutates_inventory") is False, "besliscontract mag voorraad niet muteren")
    _assert(isinstance(result.get("items"), list), "beslisitems ontbreken")
    _assert(isinstance(result.get("almost_out_items"), list), "Bijna-opitems ontbreken")
    _assert(isinstance(result.get("projection_exceptions"), list), "projectie-uitzonderingen ontbreken")
    for item in result.get("items") or []:
        _assert(str(item.get("product_type_id") or "").startswith("gpc:"), "niet-GPC Producttype in beslisresultaat")
        _assert("current_quantity" in item, "actuele Producttypevoorraad ontbreekt")
        _assert("min_stock" in item, "Producttype-minimum ontbreekt")
        _assert("ideal_stock" in item, "Producttype-streefvoorraad ontbreekt")
        _assert("amount_to_buy" in item, "Producttype-aanvulhoeveelheid ontbreekt")
    print("PASS product_type_almost_out_decision_sources")
    print("PASS product_type_almost_out_no_article_policy_fallback")
    print("PRODUCT_TYPE_ALMOST_OUT_DECISION_PHASE_E_GREEN")


if __name__ == "__main__":
    main()
