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
from app.receipt_ingestion.spaarzegels_terms import is_spaarzegels_flow_excluded
from app.services.external_candidate_diagnostics import diagnose_real_candidate_coverage
from app.services.external_database_matchers import (
    get_external_database_summary,
    list_external_database_retailers,
)
from app.services.external_database_matchflow_evidence import (
    ensure_external_receipt_item_candidates,
    match_retailer_receipt_line,
    save_matchpreview_candidates,
)
from app.services.external_product_candidate_store import (
    build_candidate_context_key,
    list_external_receipt_items,
    list_saved_external_product_candidates,
    unlink_external_catalog_links,
    promote_external_product_candidate,
)
from app.services.external_product_catalog_store import (
    list_catalog_products,
    promote_highest_candidate_to_catalog,
)
from app.services.external_receipt_auto_coverage import install_receipt_auto_candidate_coverage
from app.services.external_receipt_coverage_report import build_blind_receipt_coverage_report
from app.services.external_receipt_item_projection import install_receipt_table_line_projection
from app.services.external_relation_batch_store import (
    apply_external_relation_batch_decision,
    list_external_relation_batch_items,
)
from app.services.open_food_facts_candidate_store import save_open_food_facts_preview_candidates
from app.services.open_food_facts_search_preview import search_open_food_facts_preview

router = APIRouter()
logger = logging.getLogger('rezzerv.api')

VERSION_FILE_PATH = Path(__file__).resolve().parents[2] / 'VERSION.txt'
VERSION_TAG = VERSION_FILE_PATH.read_text(encoding='utf-8').strip() if VERSION_FILE_PATH.exists() else 'dev'


TAXONOMY_SEED_MARKERS = (
    'product_taxonomy_seed',
    'taxonomy_seed',
    'retailer_seed_file',
    'seed_file',
    'm2c2i9_seed',
    'receipt_product_intent_fallback',
)


def _is_taxonomy_seed_candidate(candidate: Any) -> bool:
    if not isinstance(candidate, dict):
        return False
    values = [
        candidate.get('candidate_source_name'),
        candidate.get('source_name'),
        candidate.get('candidate_source'),
        candidate.get('candidate_source_product_code'),
        candidate.get('source_product_code'),
        candidate.get('retailer_article_number'),
        candidate.get('variant'),
        candidate.get('candidate_status'),
        candidate.get('status'),
        candidate.get('created_by'),
        candidate.get('source'),
    ]
    haystack = ' '.join(str(value or '').strip().lower() for value in values)
    return any(marker in haystack for marker in TAXONOMY_SEED_MARKERS)


def _without_taxonomy_seed_candidates(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    next_payload = dict(payload)
    next_items = []
    removed_count = 0

    for item in list(payload.get('items') or []):
        if not isinstance(item, dict):
            next_items.append(item)
            continue

        if _is_taxonomy_seed_candidate(item) and not item.get('is_receipt_item_placeholder'):
            removed_count += 1
            continue

        next_item = dict(item)
        if isinstance(next_item.get('candidates'), list):
            filtered_candidates = []
            for candidate in next_item.get('candidates') or []:
                if _is_taxonomy_seed_candidate(candidate):
                    removed_count += 1
                    continue
                filtered_candidates.append(candidate)
            next_item['candidates'] = filtered_candidates
            next_item['candidate_count'] = len(filtered_candidates)

        next_items.append(next_item)

    next_payload['items'] = next_items
    next_payload['total'] = len(next_items)
    next_payload['taxonomy_seed_candidates_removed'] = removed_count
    return next_payload


def _is_spaarzegels_receipt_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if is_spaarzegels_flow_excluded(item):
        return True
    return is_spaarzegels_flow_excluded({
        'line_type': item.get('line_type'),
        'is_spaarzegels': item.get('is_spaarzegels'),
        'exclude_from_inventory': item.get('exclude_from_inventory'),
        'external_matching_allowed': item.get('external_matching_allowed'),
        'receipt_line_text': item.get('receipt_line_text'),
        'raw_label': item.get('raw_label') or item.get('candidate_name'),
        'normalized_label': item.get('normalized_label') or item.get('candidate_name'),
        'line_total': item.get('line_total') or item.get('price'),
        'unit_price': item.get('unit_price'),
        'price': item.get('price'),
        'quantity_label': item.get('quantity_label'),
    })


def _without_spaarzegels_receipt_items(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    next_payload = dict(payload)
    next_items = []
    removed_count = 0

    for item in list(payload.get('items') or []):
        if not isinstance(item, dict):
            next_items.append(item)
            continue

        if _is_spaarzegels_receipt_item(item):
            removed_count += 1
            continue

        next_item = dict(item)
        if isinstance(next_item.get('candidates'), list):
            filtered_candidates = []
            for candidate in next_item.get('candidates') or []:
                if _is_spaarzegels_receipt_item(candidate):
                    removed_count += 1
                    continue
                filtered_candidates.append(candidate)
            next_item['candidates'] = filtered_candidates
            next_item['candidate_count'] = len(filtered_candidates)

        next_items.append(next_item)

    next_payload['items'] = next_items
    next_payload['total'] = len(next_items)
    next_payload['spaarzegels_excluded_count'] = int(next_payload.get('spaarzegels_excluded_count') or 0) + removed_count
    return next_payload


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


@router.post('/api/external-databases/catalog/promote-candidate')
def external_databases_promote_selected_candidate(payload: dict[str, Any] = Body(default_factory=dict)):
    return promote_external_product_candidate(
        candidate_id=str(payload.get('candidate_id') or ''),
        force_overwrite=bool(payload.get('force_overwrite', False)),
    )


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


@router.post('/api/external-databases/retailers/{retailer_code}/diagnose-real-candidates')
def external_databases_diagnose_real_candidates(retailer_code: str, payload: dict[str, Any] = Body(default_factory=dict)):
    receipt_line_text = str(payload.get('receipt_line_text') or payload.get('query') or '').strip()
    include_below_threshold = bool(payload.get('include_below_threshold', True))
    if not receipt_line_text:
        raise HTTPException(status_code=400, detail='Bonregel is verplicht voor kandidatendiagnose')
    return diagnose_real_candidate_coverage(
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


@router.post('/api/external-databases/off/search-preview')
def external_databases_open_food_facts_search_preview(payload: dict[str, Any] = Body(default_factory=dict)):
    """Read-only OFF search from Rezzerv candidate evidence.

    M2C2i-25A/B: this endpoint only searches and scores Open Food Facts results.
    It must not create global products, household articles, inventory events or
    external candidate rows.
    """
    result = search_open_food_facts_preview(payload)
    if not bool(result.get('ok', True)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'OFF search-preview kon niet worden uitgevoerd')
    return result


@router.post('/api/external-databases/off/save-candidates')
def external_databases_open_food_facts_save_candidates(payload: dict[str, Any] = Body(default_factory=dict)):
    """Store OFF preview results as explicit external candidates only.

    This endpoint does not create global products, household articles or
    inventory events. Linking still requires explicit user selection.
    """
    result = save_open_food_facts_preview_candidates(payload)
    if not bool(result.get('ok', True)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'OFF kandidaten konden niet worden opgeslagen')
    return result


@router.get('/api/external-databases/receipt-items')
def external_databases_receipt_items(limit: int = Query(default=200)):
    payload = list_external_receipt_items(limit=limit)
    payload = _without_taxonomy_seed_candidates(payload)
    return _without_spaarzegels_receipt_items(payload)


@router.post('/api/external-databases/receipt-items/ensure-candidates')
def external_databases_ensure_receipt_item_candidates(payload: dict[str, Any] = Body(default_factory=dict)):
    return ensure_external_receipt_item_candidates(
        items=list(payload.get('items') or []),
        include_below_threshold=bool(payload.get('include_below_threshold', True)),
    )


@router.post('/api/external-databases/coverage/receipt-items')
def external_databases_blind_receipt_item_coverage(payload: dict[str, Any] = Body(default_factory=dict)):
    return build_blind_receipt_coverage_report(
        limit=int(payload.get('limit') or 500),
        include_below_threshold=bool(payload.get('include_below_threshold', True)),
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
    return _without_taxonomy_seed_candidates(list_saved_external_product_candidates(context_key=resolved_context_key, limit=limit))


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


@router.post('/api/external-databases/catalog/unlink')
def external_databases_unlink_catalog(payload: dict[str, Any] = Body(default_factory=dict)):
    return unlink_external_catalog_links(
        context_keys=list(payload.get('context_keys') or []),
        candidate_ids=list(payload.get('candidate_ids') or []),
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
    """Warm receipt OCR/preprocessing runtime and install receipt hooks."""
    try:
        auto_coverage_result = install_receipt_auto_candidate_coverage()
        logger.info('Automatische externe kandidaatdekking geïnstalleerd: %s', auto_coverage_result)
    except Exception as exc:
        logger.warning('Automatische externe kandidaatdekking kon niet worden geïnstalleerd: %s', exc)

    try:
        projection_result = install_receipt_table_line_projection()
        logger.info('Receipt-table-line projectie geïnstalleerd: %s', projection_result)
    except Exception as exc:
        logger.warning('Receipt-table-line projectie kon niet worden geïnstalleerd: %s', exc)

    try:
        from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import warm_receipt_image_preprocessing
        from app.services.receipt_service import warm_receipt_ocr_runtime
        preprocessing_result = warm_receipt_image_preprocessing()
        ocr_result = warm_receipt_ocr_runtime()
        logger.info('Receipt runtime warmup voltooid: preprocessing=%s ocr=%s', preprocessing_result)
    except Exception as exc:
        logger.warning('Receipt runtime warmup mislukt; upload fallback blijft actief: %s', exc)
