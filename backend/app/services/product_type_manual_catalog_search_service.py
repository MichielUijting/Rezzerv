from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.gpc_local_catalog_service import ensure_local_gpc_schema
from app.services.product_type_resolution_proposal_service import (
    build_product_type_resolution_proposals,
)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _clean(value).lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


def search_product_type_catalog(
    *,
    household_id: str,
    household_article_id: str,
    query: str,
    limit: int = 25,
) -> dict[str, Any]:
    """Zoek handmatig in de actieve GS1-GPC-catalogus zonder koppelingen vast te leggen."""
    ensure_local_gpc_schema()
    household_id = _clean(household_id)
    household_article_id = _clean(household_article_id)
    query = _clean(query)
    if not household_id:
        raise ValueError("Huishouden ontbreekt")
    if not household_article_id:
        raise ValueError("Huishoudartikel ontbreekt")
    if len(query) < 2:
        raise ValueError("Zoekterm moet minimaal twee tekens bevatten")
    limit = max(1, min(int(limit or 25), 100))

    proposals = build_product_type_resolution_proposals(household_id)
    source_item = next(
        (
            dict(item)
            for item in proposals.get("items") or []
            if _clean(item.get("household_article_id")) == household_article_id
        ),
        None,
    )
    if source_item is None:
        raise ValueError("Huishoudartikel staat niet in de actuele lijst met onopgeloste Producttypen")

    tokens = [token for token in _normalize(query).split() if token]
    if not tokens:
        raise ValueError("Zoekterm bevat geen bruikbare tekens")

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT gpc_brick_code,
                       gpc_brick_name,
                       gpc_brick_name_en,
                       gpc_class_code,
                       COALESCE(NULLIF(gpc_class_name, ''), gpc_class_name_en) AS gpc_class_name,
                       gpc_family_code,
                       COALESCE(NULLIF(gpc_family_name, ''), gpc_family_name_en) AS gpc_family_name,
                       gpc_segment_code,
                       COALESCE(NULLIF(gpc_segment_name, ''), gpc_segment_name_en) AS gpc_segment_name,
                       brick_definition_includes_en,
                       brick_definition_excludes_en,
                       language_code,
                       source_version,
                       source
                FROM gpc_product_groups
                WHERE COALESCE(active, 1) = 1
                  AND upper(COALESCE(gpc_brick_name_en, '')) NOT LIKE '%UNCLASSIFIED%'
                ORDER BY lower(COALESCE(NULLIF(gpc_brick_name, ''), gpc_brick_name_en)), gpc_brick_code
                """
            )
        ).mappings().all()

    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for row in rows:
        item = dict(row)
        searchable = _normalize(
            " ".join(
                str(item.get(key) or "")
                for key in (
                    "gpc_brick_code",
                    "gpc_brick_name",
                    "gpc_brick_name_en",
                    "gpc_class_name",
                    "gpc_family_name",
                    "gpc_segment_name",
                    "brick_definition_includes_en",
                    "brick_definition_excludes_en",
                )
            )
        )
        if not all(token in searchable for token in tokens):
            continue
        display_name = _clean(item.get("gpc_brick_name")) or _clean(item.get("gpc_brick_name_en"))
        exact_name = _normalize(display_name) == _normalize(query)
        starts_with = _normalize(display_name).startswith(_normalize(query))
        score = 3 if exact_name else 2 if starts_with else 1
        item.update(
            {
                "product_type_id": f"gpc:{item['gpc_brick_code']}",
                "display_name": display_name,
                "selection_requires_confirmation": True,
                "selected": False,
            }
        )
        ranked.append((score, display_name.lower(), item))

    ranked.sort(key=lambda entry: (-entry[0], entry[1], entry[2]["gpc_brick_code"]))
    items = [entry[2] for entry in ranked[:limit]]
    return {
        "household_id": household_id,
        "household_article_id": household_article_id,
        "inventory_name": source_item.get("inventory_name"),
        "basis": "manual_gpc_catalog_search",
        "catalog_source": "gpc_product_groups",
        "query": query,
        "read_only": True,
        "mutates_inventory": False,
        "creates_global_products": False,
        "creates_product_type_links": False,
        "selection_requires_confirmation": True,
        "result_count": len(items),
        "items": items,
    }
