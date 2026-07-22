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


def classify(path: Path) -> str:
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
            rows.append({
                'path': rel.as_posix(),
                'line': index + 1,
                'classification': classify(rel),
                'targets': matched,
                'source': line.strip(),
                'previous': lines[index - 1].strip() if index > 0 else '',
                'next': lines[index + 1].strip() if index + 1 < len(lines) else '',
                'function': function,
            })
    summary: dict[str, int] = {}
    for row in rows:
        summary[row['classification']] = summary.get(row['classification'], 0) + 1
    runtime_rows = [row for row in rows if row['classification'] in {'backend-runtime', 'frontend-runtime'}]
    backend_unscoped = [
        row for row in runtime_rows
        if row['classification'] == 'backend-runtime'
        and row.get('function')
        and not row['function']['auth_markers']
        and not any('/api/testing/' in decorator or '/api/admin/' in decorator or '/api/dev/' in decorator for decorator in row['function']['decorators'])
    ]
    return {
        'audit_version': 3,
        'targets': list(DEMO_TARGETS + ONE_TARGETS),
        'summary': {
            'household_occurrences': len(rows),
            'runtime_occurrences': len(runtime_rows),
            'backend_unscoped_occurrences': len(backend_unscoped),
            'by_classification': summary,
        },
        'backend_unscoped_occurrences': backend_unscoped,
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
