from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.gpc_local_catalog_service import ensure_local_gpc_schema
from app.services.product_type_resolution_proposal_service import build_product_type_resolution_proposals


def build_product_type_manual_selection_preview(
    household_id: str,
    *,
    household_article_id: str,
    gpc_brick_code: str,
) -> dict[str, Any]:
    """Build a read-only confirmation preview for one manual GPC selection."""
    article_id = str(household_article_id or "").strip()
    code = re.sub(r"\D+", "", str(gpc_brick_code or ""))
    if not article_id:
        raise ValueError("household_article_id is required")
    if not re.fullmatch(r"\d{8}", code):
        raise ValueError("gpc_brick_code must contain exactly 8 digits")

    proposals = build_product_type_resolution_proposals(str(household_id))
    unresolved = {
        str(item.get("household_article_id") or ""): item
        for item in proposals.get("items") or []
    }
    article = unresolved.get(article_id)
    if article is None:
        raise ValueError("household article is not an unresolved Producttype proposal")

    ensure_local_gpc_schema()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT gpc_brick_code,gpc_brick_name,gpc_brick_name_en,
                       gpc_class_code,gpc_class_name,gpc_family_code,gpc_family_name,
                       gpc_segment_code,gpc_segment_name,source_version,source
                FROM gpc_product_groups
                WHERE gpc_brick_code=:code AND COALESCE(active,1)=1
                LIMIT 1
                """
            ),
            {"code": code},
        ).mappings().first()
    if row is None:
        raise ValueError("selected GPC Brick is not active in the catalog")

    selected = dict(row)
    selected["product_type_id"] = f"gpc:{code}"
    selected["display_name"] = selected.get("gpc_brick_name") or selected.get("gpc_brick_name_en")

    return {
        "household_id": str(household_id),
        "household_article_id": article_id,
        "inventory_name": article.get("inventory_name"),
        "basis": "manual_gpc_selection_confirmation_preview",
        "selection_source": "manual_gpc_catalog_search",
        "read_only": True,
        "mutates_inventory": False,
        "creates_global_products": False,
        "creates_product_type_links": False,
        "selection_validated": True,
        "confirmation_required": True,
        "confirmation_status": "pending",
        "selected_product_type": selected,
    }
