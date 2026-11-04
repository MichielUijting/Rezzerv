"""TD-02: manually confirmed central article synonyms, Superuser/Frontteam only."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.db import engine
from app.services.session_request_context import require_platform_permission_from_session
from app.services.article_classification_sync_monitor import (
    list_sync_exceptions, retry_sync_exception,
)
from app.services.article_synonym_service import load_products, suggest_pairs, confirmed_pairs, confirm_pairs, candidate_pairs_for_product, product_link_options, unlink_pairs

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
    manual: bool = False

class ClassificationDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    left_product_id: str = Field(min_length=1, max_length=200)
    right_product_id: str = Field(min_length=1, max_length=200)
    snapshot: str = Field(pattern=r'^[0-9a-f]{64}$')
    gpc_source_id: str | None = Field(default=None, max_length=200)
    cbs_source_id: str | None = Field(default=None, max_length=200)


class BulkSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selections: list[Selection] = Field(min_length=1, max_length=200)
    decisions: list[ClassificationDecision] = Field(default_factory=list, max_length=8)

class SyncRetryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    event_id: str = Field(pattern=r'^[0-9a-f-]{36}
def list_suggestions():
    _actor('platform.external_products.view')
    with engine.connect() as conn:
        items = suggest_pairs(load_products(conn), confirmed_pairs(conn), include_name_only=True)
    return {'items': items, 'total': len(items)}


@router.get('/analysis')
def synonym_analysis():
    _actor('platform.external_products.view')
    from sqlalchemy import inspect, text
    from app.services.article_synonym_service import build_synonym_analysis
    with engine.connect() as conn:
        products = load_products(conn)
        confirmed = confirmed_pairs(conn)
        suggestions = suggest_pairs(products, confirmed, include_name_only=True)
        # An older optional classification source is not an article identity
        # authority. Some PostgreSQL installations have retired this table;
        # its absence must not hide the central Catalogus products.
        classifications = {}
        if inspect(conn).has_table('global_product_shopify_classifications'):
            classifications = {row['global_product_id']: row['shopify_path'] for row in conn.execute(text("""
                SELECT global_product_id, shopify_path
                  FROM global_product_shopify_classifications
                 WHERE is_active = TRUE
            """)).mappings()}
    return build_synonym_analysis(products, confirmed, suggestions, classifications)


@router.get('/analysis/{product_id}/candidates')
def synonym_candidates(product_id: str):
    _actor('platform.external_products.view')
    if not product_id or len(product_id) > 200:
        raise HTTPException(404, 'Catalogusartikel niet gevonden.')
    with engine.connect() as conn:
        proposals = candidate_pairs_for_product(load_products(conn), confirmed_pairs(conn), product_id)
    if proposals is None:
        raise HTTPException(404, 'Catalogusartikel niet gevonden.')
    return {'items': proposals, 'total': len(proposals), 'limit': 5}


@router.get('/analysis/{product_id}/options')
def synonym_options(product_id: str):
    _actor('platform.external_products.view')
    if not product_id or len(product_id) > 200:
        raise HTTPException(404, 'Catalogusartikel niet gevonden.')
    with engine.connect() as conn:
        options = product_link_options(load_products(conn), confirmed_pairs(conn), product_id)
    if options is None:
        raise HTTPException(404, 'Catalogusartikel niet gevonden.')
    return {'items': options, 'total': len(options)}


@router.post('/link/review')
def review_synonym_classifications(payload: BulkSelection):
    """Read-only current side-by-side verified classification comparison."""
    _actor('platform.external_products.link_existing')
    from app.services.synonym_classification_review_service import review_pairs
    with engine.connect() as conn:
        products = {p['id']: p for p in load_products(conn)}
        reviews = review_pairs(conn, [item.model_dump() for item in payload.selections], products)
    conflicts = [row for row in reviews if row['clashes']]
    if len(conflicts) > 8 or len({pid for row in conflicts for pid in
                                  (row['left_id'], row['right_id'])}) != 2 * len(conflicts):
        raise HTTPException(409, 'Controleer conflicterende synoniemen één paar tegelijk; overige selecties blijven behouden.')
    return {'items': conflicts, 'total': len(conflicts)}


@router.post('/link')
def link_suggestions(payload: BulkSelection):
    actor = _actor('platform.external_products.link_existing')
    if any(choice.gpc_source_id for choice in payload.decisions):
        # An explicit correction of an existing GPC Brick is a privileged
        # classification write, not merely permission to link synonyms.
        require_platform_permission_from_session('gpc.update')
    with engine.begin() as conn:
        return confirm_pairs(
            conn, [item.model_dump() for item in payload.selections], actor.user_id,
            decisions=[item.model_dump() for item in payload.decisions],
        )


@router.post('/unlink')
def unlink_suggestions(payload: BulkSelection):
    _actor('platform.external_products.link_existing')
    with engine.begin() as conn:
        return unlink_pairs(conn, [item.model_dump() for item in payload.selections])
)
    expected_decision_version: int = Field(ge=0)
    expected_target_version: int = Field(ge=0)
    expected_target_code: str = Field(default='', max_length=100)


@router.get('/sync-exceptions')
def sync_exceptions(limit: int = 100, offset: int = 0):
    """Internal read-only audit monitor; never a regular user work area."""
    _actor('platform.external_products.view')
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, 'Ongeldige paginering.')
    with engine.connect() as conn:
        return list_sync_exceptions(conn, limit=limit, offset=offset)


@router.post('/sync-exceptions/retry')
def retry_sync_exception_route(payload: SyncRetryRequest):
    """Explicit separate authorized transaction; never background or on GET."""
    actor = _actor('platform.external_products.link_existing')
    from sqlalchemy import text
    # GPC inheritance is a privileged GPC write; inspect the immutable event
    # before entering the write transaction, and check permission separately.
    with engine.connect() as conn:
        system = conn.execute(text("""
            SELECT classification_system FROM article_classification_sync_events
            WHERE id=:id
        """), {"id": payload.event_id}).scalar_one_or_none()
    if system == 'GPC':
        require_platform_permission_from_session('gpc.update')
    with engine.begin() as conn:
        return retry_sync_exception(
            conn, event_id=payload.event_id,
            expected_decision_version=payload.expected_decision_version,
            expected_target_version=payload.expected_target_version,
            expected_target_code=payload.expected_target_code,
            actor_id=actor.user_id,
        )


@router.get('')
def list_suggestions():
    _actor('platform.external_products.view')
    with engine.connect() as conn:
        items = suggest_pairs(load_products(conn), confirmed_pairs(conn), include_name_only=True)
    return {'items': items, 'total': len(items)}


@router.get('/analysis')
def synonym_analysis():
    _actor('platform.external_products.view')
    from sqlalchemy import inspect, text
    from app.services.article_synonym_service import build_synonym_analysis
    with engine.connect() as conn:
        products = load_products(conn)
        confirmed = confirmed_pairs(conn)
        suggestions = suggest_pairs(products, confirmed, include_name_only=True)
        # An older optional classification source is not an article identity
        # authority. Some PostgreSQL installations have retired this table;
        # its absence must not hide the central Catalogus products.
        classifications = {}
        if inspect(conn).has_table('global_product_shopify_classifications'):
            classifications = {row['global_product_id']: row['shopify_path'] for row in conn.execute(text("""
                SELECT global_product_id, shopify_path
                  FROM global_product_shopify_classifications
                 WHERE is_active = TRUE
            """)).mappings()}
    return build_synonym_analysis(products, confirmed, suggestions, classifications)


@router.get('/analysis/{product_id}/candidates')
def synonym_candidates(product_id: str):
    _actor('platform.external_products.view')
    if not product_id or len(product_id) > 200:
        raise HTTPException(404, 'Catalogusartikel niet gevonden.')
    with engine.connect() as conn:
        proposals = candidate_pairs_for_product(load_products(conn), confirmed_pairs(conn), product_id)
    if proposals is None:
        raise HTTPException(404, 'Catalogusartikel niet gevonden.')
    return {'items': proposals, 'total': len(proposals), 'limit': 5}


@router.get('/analysis/{product_id}/options')
def synonym_options(product_id: str):
    _actor('platform.external_products.view')
    if not product_id or len(product_id) > 200:
        raise HTTPException(404, 'Catalogusartikel niet gevonden.')
    with engine.connect() as conn:
        options = product_link_options(load_products(conn), confirmed_pairs(conn), product_id)
    if options is None:
        raise HTTPException(404, 'Catalogusartikel niet gevonden.')
    return {'items': options, 'total': len(options)}


@router.post('/link/review')
def review_synonym_classifications(payload: BulkSelection):
    """Read-only current side-by-side verified classification comparison."""
    _actor('platform.external_products.link_existing')
    from app.services.synonym_classification_review_service import review_pairs
    with engine.connect() as conn:
        products = {p['id']: p for p in load_products(conn)}
        reviews = review_pairs(conn, [item.model_dump() for item in payload.selections], products)
    conflicts = [row for row in reviews if row['clashes']]
    if len(conflicts) > 8 or len({pid for row in conflicts for pid in
                                  (row['left_id'], row['right_id'])}) != 2 * len(conflicts):
        raise HTTPException(409, 'Controleer conflicterende synoniemen één paar tegelijk; overige selecties blijven behouden.')
    return {'items': conflicts, 'total': len(conflicts)}


@router.post('/link')
def link_suggestions(payload: BulkSelection):
    actor = _actor('platform.external_products.link_existing')
    if any(choice.gpc_source_id for choice in payload.decisions):
        # An explicit correction of an existing GPC Brick is a privileged
        # classification write, not merely permission to link synonyms.
        require_platform_permission_from_session('gpc.update')
    with engine.begin() as conn:
        return confirm_pairs(
            conn, [item.model_dump() for item in payload.selections], actor.user_id,
            decisions=[item.model_dump() for item in payload.decisions],
        )


@router.post('/unlink')
def unlink_suggestions(payload: BulkSelection):
    _actor('platform.external_products.link_existing')
    with engine.begin() as conn:
        return unlink_pairs(conn, [item.model_dump() for item in payload.selections])
