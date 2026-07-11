from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.services.article_group_store import (
    assign_household_article_group,
    create_article_group,
    delete_article_group,
    list_article_groups,
    list_household_articles_for_grouping,
    update_article_group,
)

router = APIRouter()


@router.get('/api/article-groups')
def article_groups(
    household_id: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
):
    return list_article_groups(household_id=household_id, include_inactive=include_inactive)


@router.post('/api/article-groups')
def article_group_create(payload: dict[str, Any] = Body(default_factory=dict)):
    result = create_article_group(
        household_id=payload.get('household_id'),
        name=payload.get('name'),
    )
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Artikelgroep kon niet worden toegevoegd')
    return result


@router.put('/api/article-groups/{group_id}')
def article_group_update(group_id: str, payload: dict[str, Any] = Body(default_factory=dict)):
    result = update_article_group(
        group_id=group_id,
        household_id=payload.get('household_id'),
        name=payload.get('name'),
        status=payload.get('status'),
        sort_order=payload.get('sort_order'),
    )
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Artikelgroep kon niet worden bijgewerkt')
    return result


@router.delete('/api/article-groups/{group_id}')
def article_group_delete(group_id: str, household_id: str | None = Query(default=None)):
    result = delete_article_group(group_id=group_id, household_id=household_id)
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Artikelgroep kon niet worden verwijderd')
    return result


@router.get('/api/article-groups/household-articles')
def article_group_household_articles(household_id: str | None = Query(default=None)):
    return list_household_articles_for_grouping(household_id=household_id)


@router.put('/api/household-articles/{article_id}/article-group')
def household_article_group_update(article_id: str, payload: dict[str, Any] = Body(default_factory=dict)):
    result = assign_household_article_group(
        article_id=article_id,
        article_group_id=payload.get('article_group_id'),
        household_id=payload.get('household_id'),
    )
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Artikelgroep kon niet worden gekoppeld')
    return result
