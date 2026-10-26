"""TD-02: manually confirmed central article synonyms, Superuser/Frontteam only."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.db import engine
from app.services.session_request_context import require_platform_permission_from_session
from app.services.article_synonym_service import load_products, suggest_pairs, confirmed_pairs, confirm_pairs

router = APIRouter(prefix='/api/external-databases/article-synonyms', tags=['article-synonyms'])


def _actor(permission):
    context = require_platform_permission_from_session(permission)
    if not (context.is_platform_superuser or context.is_frontteam):
        raise HTTPException(403, 'Alleen Superusers en Frontteamleden mogen artikel-synoniemen beheren.')
    return context


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    left_product_id: str = Field(min_length=1, max_length=200)
    right_product_id: str = Field(min_length=1, max_length=200)
    fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')


class BulkSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selections: list[Selection] = Field(min_length=1, max_length=200)


@router.get('')
def list_suggestions():
    _actor('platform.external_products.view')
    with engine.connect() as conn:
        items = suggest_pairs(load_products(conn), confirmed_pairs(conn))
    return {'items': items, 'total': len(items)}


@router.post('/link')
def link_suggestions(payload: BulkSelection):
    actor = _actor('platform.external_products.link_existing')
    with engine.begin() as conn:
        return confirm_pairs(conn, [item.model_dump() for item in payload.selections], actor.user_id)
