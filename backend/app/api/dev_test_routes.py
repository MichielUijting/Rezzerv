from __future__ import annotations

from typing import Callable, Optional

from fastapi import APIRouter, Header, HTTPException

from app.schemas.testing import TestCompleteRequest, TestReportResponse, TestStartResponse, TestStatusResponse


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
