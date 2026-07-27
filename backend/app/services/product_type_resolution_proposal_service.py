from __future__ import annotations

from typing import Any

from app.services.gpc_local_catalog_service import classify_gpc_product
from app.services.product_type_operational_action_service import (
    build_product_type_operational_actions,
)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def build_product_type_resolution_proposals(household_id: str) -> dict[str, Any]:
    """Maak uitsluitend voorstellen voor onopgeloste voorraadregels; leg niets vast."""
    actions = build_product_type_operational_actions(household_id)
    next_action = dict(actions.get("next_required_action") or {})

    source_items = []
    if next_action.get("key") == "resolve_missing_global_products":
        source_items = [dict(item) for item in next_action.get("items") or []]

    proposals: list[dict[str, Any]] = []
    seen_household_articles: set[str] = set()

    for item in source_items:
        household_article_id = _clean(item.get("household_article_id"))
        if household_article_id and household_article_id in seen_household_articles:
            continue
        if household_article_id:
            seen_household_articles.add(household_article_id)

        inventory_name = _clean(item.get("inventory_name"))
        classification = classify_gpc_product(product_name=inventory_name, category="")
        proposals.append(
            {
                "household_article_id": household_article_id or None,
                "global_product_id": _clean(item.get("global_product_id")) or None,
                "inventory_name": inventory_name,
                "source_status": item.get("status"),
                "classification": classification,
                "requires_user_confirmation": True,
                "proposal_only": True,
                "global_product_created": False,
                "product_type_link_created": False,
            }
        )

    return {
        "household_id": str(household_id),
        "basis": "unresolved_inventory_product_type_proposals",
        "proposal_source": "product_type_operational_actions",
        "classifier_source": "bundled_gpc_catalog",
        "read_only": True,
        "mutates_inventory": False,
        "creates_global_products": False,
        "creates_product_type_links": False,
        "requires_user_confirmation": True,
        "source_item_count": len(source_items),
        "proposal_count": len(proposals),
        "deduplicated_by_household_article": True,
        "items": proposals,
    }
