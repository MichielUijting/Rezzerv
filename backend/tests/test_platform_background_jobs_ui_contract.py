import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROUTE_SOURCE_PATH = BACKEND_ROOT / 'app' / 'api' / 'dev_test_routes.py'

SELF_CONTAINED_BACKGROUND_ROUTES = {
    '/api/testing/regression/parsing-fixtures/run',
    '/api/testing/regression/parsing-raw/run',
}
EXTERNAL_START_MARKER_ROUTES = {
    '/api/testing/regression/smoke/run',
    '/api/testing/regression/all/run',
    '/api/testing/regression/layer1/run',
    '/api/testing/regression/layer2/run',
    '/api/testing/regression/layer3/run',
}
COMPLETION_CALLBACK_ROUTE = '/api/testing/reports/complete'
DIAGNOSTICS_REPORT_ROUTE = '/api/testing/reports/latest'


def _route_nodes() -> dict[tuple[str, str], ast.FunctionDef]:
    tree = ast.parse(ROUTE_SOURCE_PATH.read_text(encoding='utf-8'))
    routes: dict[tuple[str, str], ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.upper()
            if method not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}:
                continue
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                routes[(method, str(decorator.args[0].value))] = node
    return routes


def _call_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        if isinstance(item.func, ast.Name):
            names.add(item.func.id)
        elif isinstance(item.func, ast.Attribute):
            names.add(item.func.attr)
    return names


def test_platform_background_jobs_ui_scope_matches_self_contained_server_tasks():
    routes = _route_nodes()
    assert SELF_CONTAINED_BACKGROUND_ROUTES == {
        path for method, path in routes
        if method == 'POST' and path in SELF_CONTAINED_BACKGROUND_ROUTES
    }

    for path in SELF_CONTAINED_BACKGROUND_ROUTES:
        calls = _call_names(routes[('POST', path)])
        assert 'start_external_test' in calls
        assert 'run_receipt_parsing_baseline_suite' in calls
        assert 'complete_external_test' in calls
        assert 'get_report' in calls


def test_external_start_markers_are_not_self_contained_background_jobs():
    routes = _route_nodes()
    assert EXTERNAL_START_MARKER_ROUTES == {
        path for method, path in routes
        if method == 'POST' and path in EXTERNAL_START_MARKER_ROUTES
    }

    for path in EXTERNAL_START_MARKER_ROUTES:
        calls = _call_names(routes[('POST', path)])
        assert 'start_external_test' in calls
        assert 'run_receipt_parsing_baseline_suite' not in calls
        assert 'complete_external_test' not in calls


def test_completion_callback_and_diagnostics_read_are_not_operator_start_actions():
    routes = _route_nodes()
    completion_calls = _call_names(routes[('POST', COMPLETION_CALLBACK_ROUTE)])
    assert 'complete_external_test' in completion_calls
    assert 'start_external_test' not in completion_calls
    assert 'run_receipt_parsing_baseline_suite' not in completion_calls

    assert ('GET', DIAGNOSTICS_REPORT_ROUTE) in routes
    assert DIAGNOSTICS_REPORT_ROUTE not in SELF_CONTAINED_BACKGROUND_ROUTES
