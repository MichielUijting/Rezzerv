from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Optional

from fastapi import APIRouter, Header, HTTPException

from app.db import engine
from app.schemas.testing import TestCompleteRequest, TestReportResponse, TestStartResponse, TestStatusResponse
from app.services.receipt_status_baseline_service import validate_receipt_status_baseline

REQUIRED_KASSA_SUPERMARKET_CHAINS = {
    'ah': 'AH',
    'aldi': 'Aldi',
    'jumbo': 'Jumbo',
    'lidl': 'Lidl',
    'plus': 'Plus',
}
EXPECTED_ACTIVE_KASSA_SUPERMARKET_RECEIPTS = 14


def _normalize_chain_slug(value: Any) -> str:
    text = ''.join(ch.lower() for ch in str(value or '').strip() if ch.isalnum())
    if text in {'ah', 'albertheijn'} or 'albertheijn' in text:
        return 'ah'
    if 'aldi' in text:
        return 'aldi'
    if 'jumbo' in text:
        return 'jumbo'
    if 'lidl' in text:
        return 'lidl'
    if text == 'plus' or text.startswith('plus'):
        return 'plus'
    return text


def _passed_result(name: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {'name': name, 'status': 'passed', 'error': None, 'details': details or {}}


def _failed_result(name: str, error: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {'name': name, 'status': 'failed', 'error': error, 'details': details or {}}


def run_kassa_supermarket_regression_suite() -> list[dict[str, Any]]:
    """Admin-regressie voor de geborgde Kassa-supermarktset.

    Deze test wijzigt geen parser-, status- of databasegegevens. De runtime database
    en de bestaande SSOT-baseline blijven leidend. De test faalt bewust zodra de
    actieve supermarktset niet exact de verwachte regressiescope dekt of zodra de
    status-/baselinevergelijking niet groen is.
    """
    with engine.begin() as conn:
        validation = validate_receipt_status_baseline(conn)

    summary = validation.get('summary') or {}
    details = validation.get('details') or []
    included_scope = validation.get('included_receipt_scope') or []
    archived_scope = validation.get('excluded_archived_receipts') or []

    active_total = int(summary.get('active_receipts_total') or len(included_scope) or 0)
    archived_total = int(summary.get('archived_receipts_total') or len(archived_scope) or 0)
    chain_counts = Counter(_normalize_chain_slug(row.get('store_name')) for row in included_scope)
    chain_counts = Counter({key: value for key, value in chain_counts.items() if key in REQUIRED_KASSA_SUPERMARKET_CHAINS})
    present_chains = set(chain_counts)
    missing_chains = [label for slug, label in REQUIRED_KASSA_SUPERMARKET_CHAINS.items() if slug not in present_chains]

    non_approved_receipts = [
        {
            'source_file': row.get('source_file'),
            'store_name': row.get('store_name'),
            'parse_status': row.get('parse_status'),
        }
        for row in included_scope
        if str(row.get('parse_status') or '').strip().lower() != 'approved'
    ]

    regression_counts = {
        'different': int(summary.get('different') or 0),
        'missing': int(summary.get('missing') or 0),
        'extra': int(summary.get('extra') or 0),
        'mapping_mismatch': int(summary.get('mapping_mismatch') or 0),
        'extraction_mismatch': int(summary.get('extraction_mismatch') or 0),
        'status_logic_mismatch': int(summary.get('status_logic_mismatch') or 0),
    }
    regression_failures = {key: value for key, value in regression_counts.items() if value}

    common_details = {
        'active_receipts_total': active_total,
        'expected_active_receipts_total': EXPECTED_ACTIVE_KASSA_SUPERMARKET_RECEIPTS,
        'archived_receipts_total': archived_total,
        'required_chains': list(REQUIRED_KASSA_SUPERMARKET_CHAINS.values()),
        'chain_counts': {REQUIRED_KASSA_SUPERMARKET_CHAINS[key]: value for key, value in sorted(chain_counts.items())},
        'runtime_datastore': validation.get('runtime_datastore'),
        'baseline_file': validation.get('baseline_file'),
        'expected_status_file': validation.get('expected_status_file'),
    }

    results: list[dict[str, Any]] = []
    if active_total == EXPECTED_ACTIVE_KASSA_SUPERMARKET_RECEIPTS:
        results.append(_passed_result('Kassa supermarktset bevat 14 actieve bonnen', common_details))
    else:
        results.append(_failed_result(
            'Kassa supermarktset bevat 14 actieve bonnen',
            f'Verwacht {EXPECTED_ACTIVE_KASSA_SUPERMARKET_RECEIPTS} actieve supermarktbonnen, gevonden {active_total}.',
            common_details,
        ))

    if not missing_chains:
        results.append(_passed_result('Kassa supermarktset bevat AH, Aldi, Jumbo, Plus en Lidl', common_details))
    else:
        results.append(_failed_result(
            'Kassa supermarktset bevat AH, Aldi, Jumbo, Plus en Lidl',
            'Ontbrekende keten(s): ' + ', '.join(missing_chains),
            common_details,
        ))

    if not non_approved_receipts and active_total > 0:
        results.append(_passed_result('Alle actieve supermarktbonnen staan op Gecontroleerd', common_details))
    else:
        results.append(_failed_result(
            'Alle actieve supermarktbonnen staan op Gecontroleerd',
            f'{len(non_approved_receipts)} actieve supermarktbon(nen) staan niet op approved/Gecontroleerd.',
            {**common_details, 'non_approved_receipts': non_approved_receipts},
        ))

    if not regression_failures:
        results.append(_passed_result('SSOT-baselinevergelijking heeft geen regressieverschillen', {**common_details, 'regression_counts': regression_counts}))
    else:
        results.append(_failed_result(
            'SSOT-baselinevergelijking heeft geen regressieverschillen',
            'Regressieverschillen gevonden: ' + ', '.join(f'{key}={value}' for key, value in regression_failures.items()),
            {**common_details, 'regression_counts': regression_counts, 'failed_details': [item for item in details if item.get('result') != 'correct']},
        ))

    if archived_total >= 0:
        results.append(_passed_result('Gearchiveerde kassabonnen blijven buiten de actieve regressiescope', common_details))

    return results


def create_dev_test_router(
    *,
    require_platform_admin_user: Callable[[Optional[str]], object],
    testing_service,
    run_receipt_parsing_baseline_suite: Callable[[str], list],
) -> APIRouter:
    router = APIRouter()

    @router.post('/api/testing/regression/smoke/run', response_model=TestStartResponse)
    @router.post('/api/dev/run-smoke-tests', response_model=TestStartResponse)
    def run_smoke_tests(authorization: Optional[str] = Header(None)):
        require_platform_admin_user(authorization)
        return testing_service.start_external_test('smoke')

    @router.post('/api/testing/regression/all/run', response_model=TestStartResponse)
    @router.post('/api/dev/run-regression-tests', response_model=TestStartResponse)
    def run_regression_tests(authorization: Optional[str] = Header(None)):
        require_platform_admin_user(authorization)
        return testing_service.start_external_test('regression')

    @router.post('/api/testing/regression/layer1/run', response_model=TestStartResponse)
    @router.post('/api/dev/run-layer1-tests', response_model=TestStartResponse)
    def run_layer1_tests(authorization: Optional[str] = Header(None)):
        require_platform_admin_user(authorization)
        return testing_service.start_external_test('layer1')

    @router.post('/api/testing/regression/layer2/run', response_model=TestStartResponse)
    @router.post('/api/dev/run-layer2-tests', response_model=TestStartResponse)
    def run_layer2_tests(authorization: Optional[str] = Header(None)):
        require_platform_admin_user(authorization)
        return testing_service.start_external_test('layer2')

    @router.post('/api/testing/regression/layer3/run', response_model=TestStartResponse)
    @router.post('/api/dev/run-layer3-tests', response_model=TestStartResponse)
    def run_layer3_tests(authorization: Optional[str] = Header(None)):
        require_platform_admin_user(authorization)
        return testing_service.start_external_test('layer3')

    @router.post('/api/testing/regression/parsing-fixtures/run')
    @router.post('/api/dev/run-parsing-fixture-tests')
    def run_parsing_fixture_tests(authorization: Optional[str] = Header(None)):
        require_platform_admin_user(authorization)
        started = testing_service.start_external_test('parsing_fixture')
        if not started.get('started'):
            raise HTTPException(status_code=409, detail='Er loopt al een andere test')
        results = run_receipt_parsing_baseline_suite('fixture')
        testing_service.complete_external_test('parsing_fixture', results)
        return testing_service.get_report()

    @router.post('/api/testing/regression/parsing-raw/run')
    @router.post('/api/dev/run-parsing-raw-tests')
    def run_parsing_raw_tests(authorization: Optional[str] = Header(None)):
        require_platform_admin_user(authorization)
        started = testing_service.start_external_test('parsing_raw')
        if not started.get('started'):
            raise HTTPException(status_code=409, detail='Er loopt al een andere test')
        results = run_receipt_parsing_baseline_suite('raw')
        testing_service.complete_external_test('parsing_raw', results)
        return testing_service.get_report()

    @router.post('/api/testing/regression/kassa-supermarkets/run')
    @router.post('/api/dev/run-kassa-supermarket-regression-tests')
    def run_kassa_supermarket_regression_tests(authorization: Optional[str] = Header(None)):
        require_platform_admin_user(authorization)
        started = testing_service.start_external_test('kassa_supermarket_regression')
        if not started.get('started'):
            raise HTTPException(status_code=409, detail='Er loopt al een andere test')
        results = run_kassa_supermarket_regression_suite()
        testing_service.complete_external_test('kassa_supermarket_regression', results)
        return testing_service.get_report()

    @router.post('/api/testing/reports/complete', response_model=TestStatusResponse)
    @router.post('/api/dev/test-report', response_model=TestStatusResponse)
    def complete_test_report(payload: TestCompleteRequest):
        results = [item.model_dump() for item in payload.results]
        return testing_service.complete_external_test(payload.test_type, results)

    @router.get('/api/testing/reports/status', response_model=TestStatusResponse)
    @router.get('/api/dev/test-status', response_model=TestStatusResponse)
    def get_test_status():
        return testing_service.get_status()

    @router.get('/api/testing/reports/latest', response_model=TestReportResponse)
    @router.get('/api/dev/test-report/latest', response_model=TestReportResponse)
    def get_latest_test_report():
        return testing_service.get_report()

    return router
