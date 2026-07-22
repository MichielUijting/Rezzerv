from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

DEMO_TARGETS = ('"demo-household"', "'demo-household'")
ONE_TARGETS = ('"1"', "'1'")
TEXT_SUFFIXES = {'.py', '.js', '.jsx', '.ts', '.tsx', '.json', '.yml', '.yaml', '.md', '.sql', '.txt'}
EXCLUDED_PARTS = {'.git', 'node_modules', 'dist', 'build', '__pycache__', '.venv', 'venv'}
HOUSEHOLD_TERMS = ('household', 'huishoud', 'active_household', 'householdid')
AUTH_MARKERS = (
    'require_household_context', 'require_household_admin_context',
    'require_inventory_write_context', 'require_platform_admin_user',
    'require_household_permission', 'require_entity_household_access',
)
AUTH_BOOTSTRAP_FUNCTIONS = {
    'bootstrap_auth_registry', 'refresh_runtime_users_from_db',
    'resolve_user_household_memberships', 'login',
}
SIGNED_SOURCE_FUNCTIONS = {
    'upsert_receipt_gmail_account', 'build_receipt_gmail_account_response',
    'get_receipt_gmail_account', 'build_gmail_connect_url', 'sync_gmail_receipts',
    'handle_receipt_gmail_callback', 'import_resend_inbound_event',
}
INTERNAL_HELPERS = {
    'find_generic_existing_article_match', 'resolve_processing_article',
    'resolve_review_article_option', 'resolve_space_and_sublocation_ids',
    'create_receipt_source', 'import_shared_receipt', 'get_request_household_id',
    'resolve_authorized_household_id', '_normalize_household_id',
    'build_household_email_address',
}


def classify_path(path: Path) -> str:
    posix = path.as_posix()
    if '/testing/' in f'/{posix}' or posix.startswith('tests/') or '/tests/' in f'/{posix}':
        return 'test'
    if 'fixture' in posix.lower() or 'seed' in posix.lower():
        return 'fixture'
    if posix.startswith('docs/') or path.suffix.lower() in {'.md', '.txt'}:
        return 'documentation'
    if posix.startswith('frontend/'):
        return 'frontend-runtime'
    if posix.startswith('backend/app/'):
        return 'backend-runtime'
    return 'other'


def household_context(lines: list[str], index: int) -> str:
    return ' '.join(lines[max(0, index - 2):min(len(lines), index + 3)]).lower()


def matching_targets(lines: list[str], index: int) -> list[str]:
    line = lines[index]
    matched_demo = [target for target in DEMO_TARGETS if target in line]
    matched_one = [target for target in ONE_TARGETS if target in line]
    if matched_demo:
        return matched_demo
    context = household_context(lines, index)
    if matched_one and any(term in context for term in HOUSEHOLD_TERMS):
        return matched_one
    return []


def python_functions(source: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    functions: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = [ast.unparse(item) for item in node.decorator_list]
        function_source = ast.get_source_segment(source, node) or ''
        functions.append({
            'name': node.name,
            'start': min([node.lineno] + [item.lineno for item in node.decorator_list]),
            'end': getattr(node, 'end_lineno', node.lineno),
            'decorators': decorators,
            'auth_markers': [marker for marker in AUTH_MARKERS if marker in function_source],
        })
    return functions


def enclosing_function(functions: list[dict[str, Any]], line: int) -> dict[str, Any] | None:
    matches = [item for item in functions if item['start'] <= line <= item['end']]
    return min(matches, key=lambda item: item['end'] - item['start']) if matches else None


def fallback_category(row: dict[str, Any]) -> str:
    path = row['path']
    classification = row['classification']
    function = row.get('function') or {}
    name = str(function.get('name') or '')
    decorators = ' '.join(function.get('decorators') or [])
    lowered_path = path.lower()
    lowered_name = name.lower()

    if name == 'import_share_target_receipt':
        return 'deferred-share-target'
    if classification == 'frontend-runtime':
        return 'frontend-server-authority'
    if classification in {'test', 'fixture'}:
        return 'test-dev-fixture'
    if (
        'testing_receipt_parser_diagnosis' in lowered_path
        or 'receipt_diagnosis' in lowered_path
        or 'receipt_diagnostics' in lowered_path
        or 'receipt_po_status_delta' in lowered_path
        or any(term in lowered_name for term in ('dev_', 'regression', 'fixture', 'seed_', 'diagnos'))
        or any(prefix in decorators for prefix in ('/api/testing/', '/api/admin/', '/api/dev/'))
    ):
        return 'platform-admin-diagnostic-or-test'
    if name in AUTH_BOOTSTRAP_FUNCTIONS:
        return 'auth-bootstrap'
    if name in SIGNED_SOURCE_FUNCTIONS:
        return 'signed-state-or-server-source'
    if function.get('auth_markers'):
        return 'authenticated-route-or-helper'
    if name in INTERNAL_HELPERS:
        return 'authenticated-internal-helper'
    return 'unclassified'


def audit(root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        try:
            source = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        lines = source.splitlines()
        functions = python_functions(source) if path.suffix.lower() == '.py' else []
        for index, line in enumerate(lines):
            matched = matching_targets(lines, index)
            if not matched:
                continue
            function = enclosing_function(functions, index + 1)
            row = {
                'path': rel.as_posix(),
                'line': index + 1,
                'classification': classify_path(rel),
                'targets': matched,
                'source': line.strip(),
                'previous': lines[index - 1].strip() if index > 0 else '',
                'next': lines[index + 1].strip() if index + 1 < len(lines) else '',
                'function': function,
            }
            row['fallback_category'] = fallback_category(row)
            rows.append(row)
    runtime_rows = [row for row in rows if row['classification'] in {'backend-runtime', 'frontend-runtime'}]
    by_classification: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for row in rows:
        by_classification[row['classification']] = by_classification.get(row['classification'], 0) + 1
    for row in runtime_rows:
        category = row['fallback_category']
        by_category[category] = by_category.get(category, 0) + 1
    unclassified = [row for row in runtime_rows if row['fallback_category'] == 'unclassified']
    return {
        'audit_version': 4,
        'targets': list(DEMO_TARGETS + ONE_TARGETS),
        'summary': {
            'household_occurrences': len(rows),
            'runtime_occurrences': len(runtime_rows),
            'unclassified_runtime_occurrences': len(unclassified),
            'by_classification': by_classification,
            'by_category': by_category,
        },
        'unclassified_runtime_occurrences': unclassified,
        'runtime_occurrences': runtime_rows,
        'all_occurrences': rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    payload = audit(Path(args.root).resolve())
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(payload['summary'], ensure_ascii=False, sort_keys=True))
    print('M2C2N_HOUSEHOLD_FALLBACK_AUDIT_GREEN')


if __name__ == '__main__':
    main()
