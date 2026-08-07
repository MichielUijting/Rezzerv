"""Canonical article-option route for Uitpakken (Slice 2B2)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.db import engine
from app.services.household_article_option_service import list_canonical_household_article_options
from app.services.session_request_context import resolve_current_server_session

router = APIRouter()


@router.get('/api/store-review-articles')
def get_canonical_store_review_articles(q: str | None = Query(default=None)):
    try:
        session = resolve_current_server_session()
    except Exception as exc:
        raise HTTPException(status_code=401, detail='Geldige sessie vereist') from exc

    household_id = str(session.active_household_id or '').strip()
    if not household_id:
        raise HTTPException(status_code=403, detail='Actief huishouden ontbreekt')

    with engine.begin() as conn:
        return list_canonical_household_article_options(conn, household_id, q)
