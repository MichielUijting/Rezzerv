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



# First-screen fast path: PostgreSQL/SQLite selects only the ten household
# identities before loading their individual location-specific inventory rows.
# The small group index below supplies exact total counts and global filter
# options; no entire stock row set or GPC classification is materialized.
_IDENTITY_SQL = (
    "CASE WHEN NULLIF(TRIM(CAST(i.household_article_id AS TEXT)), '') IS NOT NULL "
    "THEN 'household:' || TRIM(CAST(i.household_article_id AS TEXT)) "
    "ELSE 'inventory:' || CAST(i.id AS TEXT) END"
)
_ACTIVE_SQL = (
    "i.household_id = :household_id "
    "AND COALESCE(i.status, 'active') = 'active' "
    "AND COALESCE(i.aantal, 0) > 0"
)
_FAST_PAGE_KEYS_SQL = f"""
WITH ranked AS (
    SELECT {_IDENTITY_SQL} AS identity_key, i.naam AS article_name,
           CAST(i.id AS TEXT) AS inventory_id,
           ROW_NUMBER() OVER (
               PARTITION BY {_IDENTITY_SQL}
               ORDER BY lower(COALESCE(i.naam, '')), i.id
           ) AS identity_rank
    FROM inventory i
    WHERE {_ACTIVE_SQL}
)
SELECT identity_key FROM ranked
WHERE identity_rank = 1
ORDER BY lower(COALESCE(NULLIF(TRIM(article_name), ''), 'Onbekend artikel')),
         inventory_id
LIMIT :page_size OFFSET :offset
"""
_FAST_GROUP_OPTIONS_SQL = f"""
SELECT {_IDENTITY_SQL} AS identity_key,
       COUNT(DISTINCT NULLIF(TRIM(s.naam), '')) AS location_count,
       MIN(NULLIF(TRIM(s.naam), '')) AS single_location,
       MIN(COALESCE(NULLIF(TRIM(ag.name), ''), 'Niet ingedeeld')) AS article_group
FROM inventory i
LEFT JOIN spaces s ON s.id = i.space_id
LEFT JOIN household_articles ha
  ON ha.id = i.household_article_id AND ha.household_id = i.household_id
LEFT JOIN article_groups ag
  ON ag.id = ha.article_group_id AND ag.household_id = i.household_id
WHERE {_ACTIVE_SQL}
GROUP BY {_IDENTITY_SQL}
"""
_FAST_SELECTED_ROWS_SQL = _STOCK_SQL.replace(
    "ORDER BY lower(COALESCE(i.naam, '')) ASC, i.id ASC",
    f"AND {_IDENTITY_SQL} IN :identity_keys\n"
    "ORDER BY lower(COALESCE(i.naam, '')) ASC, i.id ASC",
)


def _fast_mobile_page(conn, household_id, *, page, page_size, location_tracking_enabled):
    """Return all positions of at most ten identities, never the whole stock."""
    params = {"household_id": household_id}
    group_index = conn.execute(text(_FAST_GROUP_OPTIONS_SQL), params).mappings().all()
    identity_keys = conn.execute(text(_FAST_PAGE_KEYS_SQL), {
        **params, "page_size": page_size, "offset": (page - 1) * page_size,
    }).scalars().all()
    selected_rows = []
    if identity_keys:
        from sqlalchemy import bindparam

        selected_rows = [
            dict(item) for item in conn.execute(
                text(_FAST_SELECTED_ROWS_SQL).bindparams(bindparam("identity_keys", expanding=True)),
                {**params, "identity_keys": identity_keys},
            ).mappings().all()
        ]
    locations = set()
    article_groups = set()
    for group in group_index:
        count = int(group.get("location_count") or 0)
        if location_tracking_enabled and count:
            locations.add(
                "Meerdere locaties" if count > 1 else str(group.get("single_location") or "").strip()
            )
        article_groups.add(str(group.get("article_group") or "Niet ingedeeld").strip())
    total = len(group_index)
    return {
        "source_rows": selected_rows,
        "total": total,
        "inventory_total": total,
        "location_options": sorted((value for value in locations if value), key=_fold),
        "article_group_options": sorted(article_groups, key=_fold),
        "page": page,
        "page_size": page_size,
    }


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

    # For the common no-search initial view, the database paginates by
    # canonical household-article identity before returning physical rows.
    # Filtered/classification searches keep the existing exhaustive path.
    fast_page = (
        not query.strip() and not location_filter and not group_filter
        and sort_key == "name-asc"
    )
    with engine.connect() as conn:
        dialect = getattr(getattr(conn, "dialect", None), "name", "")
        if fast_page and dialect in {"postgresql", "sqlite"}:
            model = _fast_mobile_page(
                conn, household_id, page=page, page_size=page_size,
                location_tracking_enabled=location_tracking_enabled,
            )
            selected_rows = model.pop("source_rows")
            stock_rows_fetched = len(selected_rows)
            fetch_done = perf_counter()
            gpc_page = {}
        else:
            rows = [dict(row) for row in conn.execute(
                text(_STOCK_SQL), {"household_id": household_id},
            ).mappings().all()]
            fetch_done = perf_counter()
            # Classification text search must still find groups outside
            # page one; it remains explicitly more expensive than browsing.
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
            stock_rows_fetched = len(rows)
            gpc_page = gpc_all
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
            stock_rows_fetched, len(projected), model["total"],
        )
    return model
