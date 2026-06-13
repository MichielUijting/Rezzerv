"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

from pathlib import Path
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.api.route_governance import build_route_governance_manifest
from app.db import get_runtime_datastore_info
from app.services.external_database_matchers import (
    get_external_database_summary,
    list_external_database_retailers,
    match_retailer_receipt_line,
)
from app.services.external_product_candidate_store import (
    build_candidate_context_key,
    list_saved_external_product_candidates,
    save_matchpreview_candidates,
)
from app.services.external_product_catalog_store import (
    list_catalog_products,
    promote_highest_candidate_to_catalog,
)
from app.services.external_relation_batch_store import (
    apply_external_relation_batch_decision,
    list_external_relation_batch_items,
)

router = APIRouter()
logger = logging.getLogger('rezzerv.api')

VERSION_FILE_PATH = Path(__file__).resolve().parents[2] / 'VERSION.txt'
VERSION_TAG = VERSION_FILE_PATH.read_text(encoding='utf-8').strip() if VERSION_FILE_PATH.exists() else 'dev'


@router.get('/api/health')
def health():
    datastore_info = get_runtime_datastore_info()
    payload = {'status': 'ok', 'datastore': datastore_info.get('datastore', 'onbekend')}
    if datastore_info.get('database'):
        payload['database'] = datastore_info['database']
    if datastore_info.get('storage'):
        payload['storage'] = datastore_info['storage']
    return payload


@router.get('/api/version')
def api_version():
    return {
        'version': VERSION_TAG,
        'source': 'VERSION.txt',
    }


@router.get('/api/external-databases/summary')
def external_databases_summary():
    return get_external_database_summary()


@router.get('/api/external-databases/retailers')
def external_databases_retailers():
    return {'retailers': list_external_database_retailers()}


@router.post('/api/external-databases/retailers/{retailer_code}/match-preview')
def external_databases_match_preview(retailer_code: str, payload: dict[str, Any] = Body(default_factory=dict)):
    receipt_line_text = str(payload.get('receipt_line_text') or payload.get('query') or '').strip()
    include_below_threshold = bool(payload.get('include_below_threshold', True))
    if not receipt_line_text:
        raise HTTPException(status_code=400, detail='Bonregel is verplicht voor matchpreview')
    return match_retailer_receipt_line(
        retailer_code=retailer_code,
        receipt_line_text=receipt_line_text,
        include_below_threshold=include_below_threshold,
    )


@router.post('/api/external-databases/retailers/{retailer_code}/save-candidates')
def external_databases_save_candidates(retailer_code: str, payload: dict[str, Any] = Body(default_factory=dict)):
    receipt_line_text = str(payload.get('receipt_line_text') or payload.get('query') or '').strip()
    if not receipt_line_text:
        raise HTTPException(status_code=400, detail='Bonregel is verplicht om kandidaten op te slaan')
    return save_matchpreview_candidates(
        retailer_code=retailer_code,
        receipt_line_text=receipt_line_text,
        receipt_line_id=str(payload.get('receipt_line_id') or '').strip() or None,
        purchase_import_line_id=str(payload.get('purchase_import_line_id') or '').strip() or None,
        include_below_threshold=bool(payload.get('include_below_threshold', False)),
    )


@router.get('/api/external-databases/candidates')
def external_databases_saved_candidates(
    context_key: str | None = Query(default=None),
    retailer_code: str | None = Query(default=None),
    receipt_line_text: str | None = Query(default=None),
    receipt_line_id: str | None = Query(default=None),
    purchase_import_line_id: str | None = Query(default=None),
    limit: int = Query(default=50),
):
    resolved_context_key = context_key
    if not resolved_context_key and retailer_code and receipt_line_text:
        resolved_context_key = build_candidate_context_key(
            retailer_code,
            receipt_line_text,
            receipt_line_id=receipt_line_id,
            purchase_import_line_id=purchase_import_line_id,
        )
    return list_saved_external_product_candidates(context_key=resolved_context_key, limit=limit)


@router.post('/api/external-databases/catalog/promote-highest')
def external_databases_promote_highest_candidate(payload: dict[str, Any] = Body(default_factory=dict)):
    receipt_line_text = str(payload.get('receipt_line_text') or '').strip() or None
    retailer_code = str(payload.get('retailer_code') or '').strip() or None
    context_key = str(payload.get('context_key') or '').strip() or None
    threshold = float(payload.get('threshold') or 0.85)
    if not context_key and not (retailer_code and receipt_line_text):
        raise HTTPException(status_code=400, detail='Context of retailer_code + bonregel is verplicht voor cataloguskoppeling')
    return promote_highest_candidate_to_catalog(
        context_key=context_key,
        retailer_code=retailer_code,
        receipt_line_text=receipt_line_text,
        threshold=threshold,
    )


@router.get('/api/external-databases/catalog/products')
def external_databases_catalog_products(limit: int = Query(default=50)):
    return list_catalog_products(limit=limit)


@router.get('/api/admin/external-relations/batch')
def admin_external_relation_batch(household_id: str | None = Query(default=None), limit: int = Query(default=50)):
    return list_external_relation_batch_items(household_id=household_id, limit=limit)


@router.post('/api/admin/external-relations/batch/decision')
def admin_external_relation_batch_decision(payload: dict[str, Any] = Body(default_factory=dict)):
    return apply_external_relation_batch_decision(
        candidate_id=str(payload.get('candidate_id') or '').strip(),
        household_article_id=str(payload.get('household_article_id') or '').strip() or None,
        decision=str(payload.get('decision') or 'later').strip(),
        decision_reason=str(payload.get('decision_reason') or '').strip() or None,
    )


@router.get('/api/admin/route-governance')
def route_governance_manifest():
    from app.main import app
    return build_route_governance_manifest(app)



@router.on_event('startup')
def warm_receipt_runtime_at_startup():
    """Warm receipt OCR/preprocessing runtime to avoid first-upload cold-start failures."""
    try:
        from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import warm_receipt_image_preprocessing
        from app.services.receipt_service import warm_receipt_ocr_runtime
        preprocessing_result = warm_receipt_image_preprocessing()
        ocr_result = warm_receipt_ocr_runtime()
        logger.info('Receipt runtime warmup voltooid: preprocessing=%s ocr=%s', preprocessing_result, ocr_result)
    except Exception as exc:
        logger.warning('Receipt runtime warmup mislukt; upload fallback blijft actief: %s', exc)
