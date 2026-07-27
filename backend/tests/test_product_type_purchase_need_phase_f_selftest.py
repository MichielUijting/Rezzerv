from __future__ import annotations

from app.services.product_type_purchase_need_service import (
    build_product_type_purchase_needs,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    result = build_product_type_purchase_needs("1")
    _assert(result.get("basis") == "product_type", "inkoopbehoefte moet Producttype als basis gebruiken")
    _assert(result.get("need_source") == "product_type_almost_out_decision", "onjuiste behoeftebron")
    _assert(result.get("article_policy_fallback") is False, "artikelgebonden fallback is verboden")
    _assert(result.get("concrete_article_selection_deferred") is True, "concreet artikel moet later worden gekozen")
    _assert(result.get("read_only") is True, "projectie moet read-only zijn")
    _assert(result.get("mutates_inventory") is False, "projectie mag voorraad niet muteren")
    _assert(result.get("mutates_purchase_list") is False, "projectie mag inkooplijst niet muteren")
    _assert(isinstance(result.get("items"), list), "behoefte-items ontbreken")
    _assert(isinstance(result.get("projection_exceptions"), list), "projectie-uitzonderingen ontbreken")
    for item in result.get("items") or []:
        _assert(bool(item.get("product_type_id")), "Producttype ontbreekt")
        _assert(float(item.get("required_quantity") or 0) > 0, "behoeftehoeveelheid moet positief zijn")
        _assert(item.get("concrete_article_selected") is False, "concreet artikel mag niet vooraf gekozen zijn")
        _assert(item.get("global_product_id") is None, "universeel artikel mag nog niet gekozen zijn")
        _assert(item.get("gtin") is None, "GTIN mag nog niet gekozen zijn")
        _assert(item.get("household_article_id") is None, "huishoudartikel mag nog niet gekozen zijn")
    print("PASS product_type_purchase_need_source")
    print("PASS product_type_purchase_need_defers_article_selection")
    print("PRODUCT_TYPE_PURCHASE_NEED_PHASE_F_GREEN")


if __name__ == "__main__":
    main()
