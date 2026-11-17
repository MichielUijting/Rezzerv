"""Read-only, household-scoped paged stock projection for mobile Voorraad.

Stock records are grouped by household_article_id (or inventory id when
unlinked) BEFORE paging. This keeps all location-specific inventory targets of
one article together. The original unpaged preview endpoint is unchanged.
"""
from __future__ import annotations

import logging
import unicodedata
from time import perf_counter

from fastapi import APIRouter, Header, Query
from sqlalchemy import text

from app.db import engine
from app.services.dutch_gpc_projection_service import dutch_gpc_by_household_article

router = APIRouter()

_STOCK_SQL = """
SELECT i.id, i.naam AS artikel, i.aantal, i.household_article_id,
       i.space_id, i.sublocation_id,
       s.naam AS locatie, sl.naam AS sublocatie,
       ag.name AS article_group_name
FROM inventory i
LEFT JOIN spaces s ON s.id = i.space_id
LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
LEFT JOIN household_articles ha
  ON ha.id = i.household_article_id AND ha.household_id = i.household_id
LEFT JOIN article_groups ag
  ON ag.id = ha.article_group_id AND ag.household_id = i.household_id
WHERE i.household_id = :household_id
  AND COALESCE(i.status, 'active') = 'active'
  AND COALESCE(i.aantal, 0) > 0
ORDER BY lower(COALESCE(i.naam, '')) ASC, i.id ASC
"""


def _fold(value):
    raw = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
    return "".join(char for char in raw if not unicodedata.combining(char))


def _group_rows(rows, gpc_map=None):
    """Same identity/quantity/location aggregation as mobile buildMobileInventoryRows."""
    groups = {}
    for source_index, raw in enumerate(rows):
        item = dict(raw)
        try:
            quantity = float(item.get("aantal") or 0)
        except (TypeError, ValueError):
            continue
        if quantity <= 0:
            continue
        article_id = str(item.get("household_article_id") or "").strip()
        inventory_id = str(item.get("id") or "").strip()
        key = f"household:{article_id}" if article_id else f"inventory:{inventory_id or source_index}"
        name = str(item.get("household_article_name") or item.get("artikel") or "").strip()
        product_name = str(item.get("product_name") or item.get("artikel") or "").strip()
        location = str(item.get("locatie") or "").strip()
        sublocation = str(item.get("sublocatie") or "").strip()
        gpc = (gpc_map or {}).get(article_id, {})
        row = groups.get(key)
        if row is None:
            row = {
                "key": key,
                "rows": [],
                "household_name": name or product_name or "Onbekend artikel",
                "product_name": product_name,
                "article_group": str(item.get("article_group_name") or "").strip() or "Niet ingedeeld",
                "gpc_brick": str(gpc.get("gpc_brick_name") or item.get("gpc_brick_name") or "").strip(),
                "gpc_class": str(gpc.get("gpc_class_name") or item.get("gpc_class_name") or "").strip(),
                "gpc_family": str(gpc.get("gpc_family_name") or item.get("gpc_family_name") or "").strip(),
                "locations": set(),
                "sublocations": set(),
                "first_seen_index": source_index,
            }
            groups[key] = row
        row["rows"].append(item)
        if location:
            row["locations"].add(location)
        if sublocation:
            row["sublocations"].add(f"{location}__{sublocation}")
    for row in groups.values():
        locations = sorted(row["locations"])
        sublocations = sorted(row["sublocations"])
        row["location"] = "Meerdere locaties" if len(locations) > 1 else (locations[0] if locations else "Geen locatie")
        row["sublocation"] = "Meerdere sublocaties" if len(sublocations) > 1 else (
            sublocations[0].split("__", 1)[1] if sublocations else ""
        )
    return list(groups.values())


def _project_page(
    rows, *, page=1, page_size=10, query="", location_filter="",
    group_filter="", sort_key="name-asc", location_tracking_enabled=True, gpc_map=None,
):
    groups = _group_rows(rows, gpc_map=gpc_map)
    locations = sorted(
        {item["location"] for item in groups if item["location"] != "Geen locatie"},
        key=_fold,
    ) if location_tracking_enabled else []
    article_groups = sorted({item["article_group"] for item in groups}, key=_fold)

    q = _fold(query)
    subset = []
    for item in groups:
        if location_tracking_enabled and location_filter and item["location"] != location_filter:
            continue
        if group_filter and item["article_group"] != group_filter:
            continue
        if q:
            searchable = [
                item["household_name"], item["product_name"], item["article_group"],
                item["gpc_brick"], item["gpc_class"], item["gpc_family"],
            ]
            if location_tracking_enabled:
                searchable.extend((item["location"], item["sublocation"]))
            if not any(q in _fold(v) for v in searchable):
                continue
        subset.append(item)

    if sort_key == "location" and location_tracking_enabled:
        subset.sort(key=lambda item: (
            _fold(item["location"]), _fold(item["household_name"]), item["first_seen_index"],
        ))
    elif sort_key == "name-desc":
        # Stable descending name sort, with deterministic identity fallback.
        subset.sort(key=lambda item: (_fold(item["household_name"]), item["first_seen_index"]), reverse=True)
    else:
        subset.sort(key=lambda item: (_fold(item["household_name"]), item["first_seen_index"]))

    start = (page - 1) * page_size
    selected = subset[start:start + page_size]
    return {
        "source_rows": [line for group in selected for line in group["rows"]],
        "total": len(subset),
        "inventory_total": len(groups),
        "location_options": locations,
        "article_group_options": article_groups,
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/voorraad/mobile-page")
def mobile_inventory_page(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=10),
    query: str = Query(default="", max_length=200),
    location_filter: str = Query(default="", max_length=200),
    group_filter: str = Query(default="", max_length=200),
    sort_key: str = Query(default="name-asc", pattern="^(name-asc|name-desc|location)$"),
    location_tracking_enabled: bool = Query(default=True),
    authorization: str | None = Header(default=None),
):
    from app import main as legacy

    started = perf_counter()
    runtime_context = legacy.require_household_context(authorization)
    household_context = legacy.household_context_from_runtime_context(runtime_context)
    household_id = household_context.active_household_id

    # This first query uses only light list fields, not the expensive GPC
    # projection. One household/identity may have many underlying stock rows.
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(
            text(_STOCK_SQL), {"household_id": household_id},
        ).mappings().all()]
        fetch_done = perf_counter()
        # Classification-dependent search legitimately needs GPC for the full
        # candidate set. Normal page and location/group filters do not.
        gpc_all = dutch_gpc_by_household_article(
            conn, household_id,
            [row.get("household_article_id") for row in rows],
        ) if query.strip() else {}
        model = _project_page(
            rows, page=page, page_size=page_size, query=query,
            location_filter=location_filter, group_filter=group_filter,
            sort_key=sort_key, location_tracking_enabled=location_tracking_enabled,
            gpc_map=gpc_all,
        )
        selected_rows = model.pop("source_rows")
        selected_ids = [row.get("household_article_id") for row in selected_rows]
        gpc_page = gpc_all if query.strip() else dutch_gpc_by_household_article(
            conn, household_id, selected_ids,
        )
    # Preserve the original preview JSON properties for the mobile projector.
    projected = []
    for row in selected_rows:
        normalized = legacy._dev_inventory_preview_row({
            **row,
            **gpc_page.get(str(row.get("household_article_id") or "").strip(), {}),
        })
        normalized["article_group_name"] = str(row.get("article_group_name") or "").strip() or "Niet ingedeeld"
        projected.append(normalized)
    model["rows"] = projected
    elapsed = perf_counter() - started
    if elapsed >= 0.5:
        logging.getLogger("uvicorn.error").info(
            "mobile_inventory_page_ms=%.1f lightweight_rows_ms=%.1f "
            "project_ms=%.1f source_rows=%d sent_rows=%d groups=%d",
            elapsed * 1000, (fetch_done - started) * 1000,
            (perf_counter() - fetch_done) * 1000,
            len(rows), len(projected), model["total"],
        )
    return model
