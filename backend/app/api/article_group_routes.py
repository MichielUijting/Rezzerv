from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query

from app.services.article_group_store import (
    assign_household_article_group,
    create_article_group,
    delete_article_group,
    list_article_groups,
    list_household_articles_for_grouping,
    update_article_group,
)

router = APIRouter()

_require_household_context: Callable[..., dict] | None = None
_require_household_admin_context: Callable[..., dict] | None = None
_require_article_group_create_context: Callable[..., dict] | None = None


def configure_article_group_routes(
    *,
    require_household_context: Callable[..., dict],
    require_household_admin_context: Callable[..., dict],
    require_article_group_create_context: Callable[..., dict],
) -> None:
    global _require_household_context
    global _require_household_admin_context
    global _require_article_group_create_context

    _require_household_context = require_household_context
    _require_household_admin_context = require_household_admin_context
    _require_article_group_create_context = require_article_group_create_context


def _configured_callbacks() -> tuple[Callable[..., dict], Callable[..., dict], Callable[..., dict]]:
    if (
        _require_household_context is None
        or _require_household_admin_context is None
        or _require_article_group_create_context is None
    ):
        raise RuntimeError('Artikelgroep-routes zijn niet geconfigureerd')
    return (
        _require_household_context,
        _require_household_admin_context,
        _require_article_group_create_context,
    )


def _active_household_id(context: dict) -> str:
    household_id = str(context.get('active_household_id') or '').strip()
    if not household_id:
        raise HTTPException(status_code=403, detail='Geen actief huishouden beschikbaar')
    return household_id


@router.get('/api/article-groups')
def article_groups(
    household_id: str | None = Query(default=None),
    authorization: Optional[str] = Header(None),
):
    require_context, _, _ = _configured_callbacks()
    context = require_context(authorization, requested_household_id=household_id)
    return list_article_groups(household_id=_active_household_id(context))


@router.post('/api/article-groups')
def article_group_create(
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: Optional[str] = Header(None),
):
    _, _, require_create_context = _configured_callbacks()
    context = require_create_context(
        authorization,
        requested_household_id=payload.get('household_id'),
    )
    result = create_article_group(
        household_id=_active_household_id(context),
        name=payload.get('name'),
    )
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Artikelgroep kon niet worden toegevoegd')
    return result


@router.put('/api/article-groups/{group_id}')
def article_group_update(
    group_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: Optional[str] = Header(None),
):
    _, require_admin_context, _ = _configured_callbacks()
    context = require_admin_context(
        authorization,
        requested_household_id=payload.get('household_id'),
    )
    result = update_article_group(
        group_id=group_id,
        household_id=_active_household_id(context),
        name=payload.get('name'),
        sort_order=payload.get('sort_order'),
    )
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Artikelgroep kon niet worden bijgewerkt')
    return result


@router.delete('/api/article-groups/{group_id}')
def article_group_delete(
    group_id: str,
    household_id: str | None = Query(default=None),
    authorization: Optional[str] = Header(None),
):
    _, require_admin_context, _ = _configured_callbacks()
    context = require_admin_context(
        authorization,
        requested_household_id=household_id,
    )
    result = delete_article_group(
        group_id=group_id,
        household_id=_active_household_id(context),
    )
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Artikelgroep kon niet worden verwijderd')
    return result


@router.get('/api/article-groups/household-articles')
def article_group_household_articles(
    household_id: str | None = Query(default=None),
    authorization: Optional[str] = Header(None),
):
    require_context, _, _ = _configured_callbacks()
    context = require_context(authorization, requested_household_id=household_id)
    return list_household_articles_for_grouping(
        household_id=_active_household_id(context),
    )


@router.put('/api/household-articles/{article_id}/article-group')
def household_article_group_update(
    article_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: Optional[str] = Header(None),
):
    require_context, _, _ = _configured_callbacks()
    context = require_context(
        authorization,
        requested_household_id=payload.get('household_id'),
    )
    if str(context.get('display_role') or '').strip().lower() == 'viewer':
        raise HTTPException(
            status_code=403,
            detail='Kijkers mogen de artikelgroep niet wijzigen',
        )
    result = assign_household_article_group(
        article_id=article_id,
        article_group_id=payload.get('article_group_id'),
        household_id=_active_household_id(context),
    )
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Artikelgroep kon niet worden gekoppeld')
    return result
