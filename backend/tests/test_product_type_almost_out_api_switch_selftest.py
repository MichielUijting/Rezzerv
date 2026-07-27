from __future__ import annotations

import inspect

from app.api import product_inventory_group_routes
from app.services.product_type_almost_out_decision_service import (
    build_product_type_almost_out_decision,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    source = inspect.getsource(product_inventory_group_routes.product_type_almost_out_preview)
    _assert(
        "build_product_type_almost_out_decision" in source,
        "Bijna-op previewroute gebruikt niet de Producttypebeslisservice",
    )
    _assert(
        "build_product_type_almost_out_preview" not in source,
        "Bijna-op previewroute gebruikt nog de oude previewservice",
    )
    print("PASS product_type_almost_out_api_source")

    result = build_product_type_almost_out_decision("1")
    _assert(result.get("basis") == "product_type", "API-beslisbasis is niet Producttype")
    _assert(result.get("article_policy_fallback") is False, "Artikelbeleidsfallback staat nog aan")
    _assert(result.get("policy_source") == "household_product_type_settings", "Verkeerde beleidsbron")
    _assert(result.get("inventory_source") == "product_type_inventory_projection", "Verkeerde voorraadbron")
    print("PASS product_type_almost_out_api_contract")

    print("PRODUCT_TYPE_ALMOST_OUT_API_SWITCH_GREEN")


if __name__ == "__main__":
    main()
