from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text


_EVENTS_PATH = "/api/household-articles/{household_article_id}/events"


def load_household_article_events(conn, household_id: str, household_article_id: str) -> dict[str, Any]:
    """Load one household article's inventory history with PostgreSQL-native ordering."""

    normalized_household_id = str(household_id or "").strip()
    normalized_article_id = str(household_article_id or "").strip()
    if not normalized_household_id:
        raise HTTPException(status_code=400, detail="Actief huishouden ontbreekt")
    if not normalized_article_id:
        raise HTTPException(status_code=400, detail="Artikel-id ontbreekt")

    article = conn.execute(
        text(
            """
            SELECT id, name
            FROM household_articles
            WHERE id = :household_article_id
              AND household_id = :household_id
              AND COALESCE(status, 'active') = 'active'
            LIMIT 1
            """
        ),
        {
            "household_article_id": normalized_article_id,
            "household_id": normalized_household_id,
        },
    ).mappings().first()
    if not article:
        raise HTTPException(status_code=404, detail="Artikel niet gevonden")

    article_name = str(article.get("name") or "").strip()
    rows = conn.execute(
        text(
            """
            SELECT
                id,
                article_id,
                household_article_id,
                article_name,
                location_id,
                location_label,
                event_type,
                quantity,
                old_quantity,
                new_quantity,
                source,
                note,
                created_at
            FROM inventory_events
            WHERE household_id = :household_id
              AND (
                household_article_id = :household_article_id
                OR article_id = :household_article_id
                OR lower(trim(article_name)) = lower(trim(:article_name))
              )
            ORDER BY created_at DESC NULLS LAST, id DESC
            """
        ),
        {
            "household_id": normalized_household_id,
            "household_article_id": normalized_article_id,
            "article_name": article_name,
        },
    ).mappings().all()

    return {
        "article_id": normalized_article_id,
        "items": [dict(row) for row in rows],
    }


def install_household_article_events_postgresql_contract(main_module) -> None:
    """Replace the legacy SQLite datetime()-ordered article-history route."""

    def get_household_article_events_postgresql(
        household_article_id: str,
        authorization: str | None = None,
    ):
        context = main_module.require_household_context(authorization)
        household_id = str(context.get("active_household_id") or "").strip()
        with main_module.engine.begin() as conn:
            return load_household_article_events(
                conn,
                household_id,
                household_article_id,
            )

    patched_route = False
    for route in main_module.app.routes:
        if (
            getattr(route, "path", None) == _EVENTS_PATH
            and "GET" in (getattr(route, "methods", set()) or set())
        ):
            route.endpoint = get_household_article_events_postgresql
            if getattr(route, "dependant", None) is not None:
                route.dependant.call = get_household_article_events_postgresql
            patched_route = True
            break

    if not patched_route:
        raise RuntimeError("Household article events-route niet gevonden voor PostgreSQL-contract")
