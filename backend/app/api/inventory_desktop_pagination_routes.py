"""Fast, household-scoped first-page projection for desktop Voorraad.

Desktop groups active positive inventory by normalized *inventory name*, not by
household article ID. Group keys are selected with LIMIT/OFFSET in SQL before
loading the physical stock positions belonging to the ten visible groups.
This is an additive read route: legacy inventory editing/detail endpoints stay
unchanged. GPC is fetched separately, after the basic first page is visible.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Header, HTTPException, Query
from sqlalchemy import bindparam, text

from app.db import engine
from app.services.dutch_gpc_projection_service import dutch_gpc_by_household_article


router = APIRouter()

# This matches frontend mergeInventoryRows(): trim/lower name, distinct
# inventory ID for an unnamed item. Do not merge different household articles
# by barcode or product identity here; desktop's existing grouping is by name.
_DESKTOP_GROUP_KEY = (
    "CASE WHEN TRIM(COALESCE(i.naam, '')) <> '' "
    "THEN 'name:' || lower(TRIM(i.naam)) "
    "ELSE 'inventory:' || CAST(i.id AS TEXT) END"
)
_DESKTOP_WHERE = (
    "i.household_id = :household_id "
    "AND COALESCE(i.status, 'active') = 'active' "
    "AND COALESCE(i.aantal, 0) > 0"
)
_GROUPED_SQL = f"""
SELECT {_DESKTOP_GROUP_KEY} AS group_key,
       MIN(lower(COALESCE(i.naam, ''))) AS sort_name,
       MIN(CAST(i.id AS TEXT)) AS sort_id
FROM inventory i
WHERE {_DESKTOP_WHERE}
GROUP BY {_DESKTOP_GROUP_KEY}
"""
_DESKTOP_COUNT_SQL = f"SELECT COUNT(*) FROM ({_GROUPED_SQL}) groups"
_DESKTOP_PAGE_KEYS_SQL = (
    f"SELECT group_key FROM ({_GROUPED_SQL}) groups "
    "ORDER BY sort_name, sort_id LIMIT :page_size OFFSET :offset"
)
_DESKTOP_VISIBLE_ROWS_SQL = f"""
SELECT i.id, i.naam AS artikel, i.aantal, i.household_article_id,
       i.space_id, i.sublocation_id,
       s.naam AS locatie, sl.naam AS sublocatie
FROM inventory i
LEFT JOIN spaces s ON s.id = i.space_id
LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
WHERE {_DESKTOP_WHERE}
  AND {_DESKTOP_GROUP_KEY} IN :group_keys
ORDER BY lower(COALESCE(i.naam, '')) ASC, i.id ASC
"""


def _select_desktop_page(conn, household_id: str, *, page: int, page_size: int) -> dict:
    """Return exactly one page of *complete* name groups, plus global total."""
    params = {"household_id": household_id}
    total = int(conn.execute(text(_DESKTOP_COUNT_SQL), params).scalar() or 0)
    keys = conn.execute(text(_DESKTOP_PAGE_KEYS_SQL), {
        **params,
        "page_size": page_size,
        "offset": (page - 1) * page_size,
    }).scalars().all()
    rows = []
    if keys:
        rows = [
            dict(item)
            for item in conn.execute(
                text(_DESKTOP_VISIBLE_ROWS_SQL).bindparams(
                    bindparam("group_keys", expanding=True)
                ),
                {**params, "group_keys": keys},
            ).mappings().all()
        ]
    return {"rows": rows, "total": total, "page": page, "page_size": page_size}


def _household_id_for_request(authorization: str | None) -> str:
    # Same fail-closed authorization and active-household context as the
    # canonical legacy inventory preview; never trust a client household ID.
    from app import main as legacy

    runtime_context = legacy.require_household_context(authorization)
    context = legacy.household_context_from_runtime_context(runtime_context)
    return context.active_household_id


@router.get("/api/voorraad/desktop-page")
def desktop_inventory_page(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=10),
    authorization: str | None = Header(default=None),
):
    from app import main as legacy

    household_id = _household_id_for_request(authorization)
    with engine.connect() as conn:
        page_data = _select_desktop_page(
            conn, household_id, page=page, page_size=page_size,
        )
    page_data["rows"] = [
        legacy._dev_inventory_preview_row(row) for row in page_data["rows"]
    ]
    return page_data


@router.post("/api/voorraad/desktop-page-classifications")
def desktop_inventory_page_classifications(
    household_article_ids: list[str] = Body(embed=True),
    authorization: str | None = Header(default=None),
):
    """Enrich visible rows after first paint; preserve canonical GPC semantics."""
    household_id = _household_id_for_request(authorization)
    ids = list(dict.fromkeys(
        str(value or "").strip()
        for value in household_article_ids
        if str(value or "").strip()
    ))
    if len(ids) > 200:
        raise HTTPException(status_code=422, detail="Te veel artikelen voor één pagina.")
    if not ids:
        return {"by_article": {}}
    # The GPC service itself restricts lookup to the active household; the
    # transaction matches the established preview's assignment behavior.
    with engine.begin() as conn:
        projection = dutch_gpc_by_household_article(conn, household_id, ids)
    return {"by_article": projection}
