from __future__ import annotations

from app.services.product_type_inventory_projection_service import (
    build_product_type_inventory_projection,
)
from app.services.product_type_resolution_service import resolve_product_type
from app.services.product_type_unit_conversion_service import convert_quantity


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    empty_resolution = resolve_product_type()
    _assert(empty_resolution.get("status") == "missing_household_article", "lege resolverstatus onjuist")
    _assert(empty_resolution.get("read_only") is True, "resolver moet read-only zijn")
    _assert(empty_resolution.get("mutates_inventory") is False, "resolver mag voorraad niet muteren")
    print("PASS product_type_central_resolver_contract")

    _assert(convert_quantity(1.0, "kg", "g") == 1000.0, "kg naar g conversie onjuist")
    _assert(convert_quantity(1.0, "liter", "ml") == 1000.0, "liter naar ml conversie onjuist")
    _assert(convert_quantity(1.0, "stuk", "ml") is None, "incompatibele conversie moet blokkeren")
    print("PASS product_type_unit_conversion_contract")

    projection = build_product_type_inventory_projection("1")
    _assert(projection.get("basis") == "product_type", "projectiebasis onjuist")
    _assert(projection.get("read_only") is True, "projectie moet read-only zijn")
    _assert(projection.get("mutates_inventory") is False, "projectie mag voorraad niet muteren")
    _assert(isinstance(projection.get("items"), list), "projectie-items ontbreken")
    _assert(isinstance(projection.get("exceptions"), list), "projectie-uitzonderingen ontbreken")
    source_rows = int(projection.get("source_inventory_rows") or 0)
    projected_rows = int(projection.get("projected_inventory_rows") or 0)
    excluded_rows = int(projection.get("excluded_inventory_rows") or 0)
    _assert(source_rows == projected_rows + excluded_rows, "projectie verantwoordt niet alle voorraadregels")
    print("PASS product_type_inventory_projection_contract")

    print("PRODUCT_TYPE_FOUNDATION_PHASE_D_GREEN")


if __name__ == "__main__":
    main()
