from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

ROOT = Path.cwd()
OUTPUT_DIR = ROOT / 'tools' / 'receipt_csv_poc' / 'reports'
JSON_OUTPUT = OUTPUT_DIR / 'receipt_diagnostics_dependency_inventory.json'
MD_OUTPUT = OUTPUT_DIR / 'receipt_diagnostics_dependency_inventory.md'

SCAN_EXTENSIONS = {
    '.py', '.jsx', '.js', '.ts', '.tsx', '.ps1', '.bat', '.cmd', '.md', '.txt', '.json', '.html'
}

EXCLUDED_PARTS = {
    '.git', 'node_modules', '__pycache__', '.pytest_cache', '.venv', 'venv', 'dist', 'build'
}

ROUTE_PATTERNS = {
    'canonical': [
        '/api/receipt-diagnostics',
        '/api/receipt-diagnostics/route-inventory',
        '/api/receipt-diagnostics/line-quality',
        '/api/receipt-diagnostics/line-quality/download',
        '/api/receipt-diagnostics/parser-quality',
        '/api/receipt-diagnostics/parser-quality/download',
        '/api/receipt-diagnostics/kpi',
        '/api/receipt-diagnostics/kpi/scope',
        '/api/receipt-diagnostics/import-dry-run',
        '/api/receipt-diagnostics/import-dry-run/health',
    ],
    'legacy': [
        '/api/testing/receipt-line-diagnosis',
        '/api/testing/receipt-line-diagnosis/download',
        '/api/testing/receipt-parser-diagnosis',
        '/api/testing/receipt-parser-diagnosis/download',
        '/api/receipt-import-diagnosis/health',
        '/api/receipt-import-diagnosis/zip-dry-run',
        '/api/receipt-kpi/baseline',
        '/api/receipt-kpi/scope-diagnosis',
    ],
    'temporary_forbidden': [
        '/api/testing/receipt-filter-selftest',
        '/api/testing/receipt-line-flow-trace',
        '/api/testing/receipt-table-schema',
        '/api/testing/reset-active-receipt-testset',
    ],
}

# Also catch split/string-fragment references without exact literal path.
TOKEN_PATTERNS = {
    'receipt_diagnostics_router': 'canonical',
    'receipt_diagnosis_router': 'legacy',
    'receipt_kpi_router': 'legacy',
    'receipt_import_diagnosis_router': 'legacy',
    'receipt_diagnostics_routes': 'canonical',
    'receipt_diagnosis_routes': 'legacy',
    'receipt_kpi_routes': 'legacy',
    'receipt_import_diagnosis_routes': 'legacy',
    'receipt-line-diagnosis': 'legacy',
    'receipt-parser-diagnosis': 'legacy',
    'receipt-import-diagnosis': 'legacy',
    'receipt-kpi': 'legacy',
    'receipt-diagnostics': 'canonical',
    'receipt-filter-selftest': 'temporary_forbidden',
    'receipt-line-flow-trace': 'temporary_forbidden',
    'receipt-table-schema': 'temporary_forbidden',
    'reset-active-receipt-testset': 'temporary_forbidden',
}


def iter_files() -> Iterable[Path]:
    for path in ROOT.rglob('*'):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCAN_EXTENSIONS:
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        # Do not let prior reports count as dependencies.
        if path == JSON_OUTPUT or path == MD_OUTPUT:
            continue
        yield path


def line_snippet(line: str) -> str:
    return re.sub(r'\s+', ' ', line.strip())[:240]


def classify_path(path: Path) -> str:
    text = path.as_posix()
    if text.startswith('frontend/'):
        return 'frontend'
    if text.startswith('backend/app/api/'):
        return 'backend_api'
    if text.startswith('backend/'):
        return 'backend'
    if text.endswith('.ps1') or text.endswith('.bat') or text.endswith('.cmd'):
        return 'script'
    if text.endswith('.md') or text.endswith('.txt'):
        return 'documentation'
    if text.startswith('tools/'):
        return 'tooling'
    return 'other'


def scan() -> dict:
    route_hits: list[dict] = []
    by_file: dict[str, dict] = {}
    counts = defaultdict(int)

    all_literals: dict[str, str] = {}
    for category, routes in ROUTE_PATTERNS.items():
        for route in routes:
            all_literals[route] = category

    for path in iter_files():
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        relative = path.relative_to(ROOT).as_posix()
        file_hits: list[dict] = []
        lines = text.splitlines()
        for idx, line in enumerate(lines, start=1):
            for route, category in all_literals.items():
                if route in line:
                    hit = {
                        'file': relative,
                        'area': classify_path(path.relative_to(ROOT)),
                        'line': idx,
                        'category': category,
                        'match_type': 'route_literal',
                        'match': route,
                        'snippet': line_snippet(line),
                    }
                    route_hits.append(hit)
                    file_hits.append(hit)
                    counts[category] += 1
            for token, category in TOKEN_PATTERNS.items():
                if token in line:
                    hit = {
                        'file': relative,
                        'area': classify_path(path.relative_to(ROOT)),
                        'line': idx,
                        'category': category,
                        'match_type': 'token',
                        'match': token,
                        'snippet': line_snippet(line),
                    }
                    route_hits.append(hit)
                    file_hits.append(hit)
                    counts[category] += 1
        if file_hits:
            categories = sorted({hit['category'] for hit in file_hits})
            by_file[relative] = {
                'area': classify_path(path.relative_to(ROOT)),
                'categories': categories,
                'hit_count': len(file_hits),
                'hits': file_hits,
            }

    recommendations = build_recommendations(by_file)
    return {
        'success': True,
        'diagnostic_only': True,
        'parser_changed': False,
        'status_classification_changed': False,
        'database_changed': False,
        'ui_changed': False,
        'summary': {
            'files_with_hits': len(by_file),
            'total_hits': len(route_hits),
            'canonical_hits': counts['canonical'],
            'legacy_hits': counts['legacy'],
            'temporary_forbidden_hits': counts['temporary_forbidden'],
        },
        'route_patterns': ROUTE_PATTERNS,
        'files': by_file,
        'recommendations': recommendations,
    }


def build_recommendations(by_file: dict[str, dict]) -> dict:
    legacy_files = [path for path, info in by_file.items() if 'legacy' in info['categories']]
    forbidden_files = [path for path, info in by_file.items() if 'temporary_forbidden' in info['categories']]
    canonical_files = [path for path, info in by_file.items() if 'canonical' in info['categories']]

    frontend_legacy = [path for path in legacy_files if by_file[path]['area'] == 'frontend']
    scripts_legacy = [path for path in legacy_files if by_file[path]['area'] in {'script', 'tooling'}]
    backend_legacy = [path for path in legacy_files if by_file[path]['area'] in {'backend_api', 'backend'}]

    return {
        'safe_now': [
            'Do not remove legacy routes yet; keep them until frontend/scripts are migrated.',
            'Keep /api/receipt-diagnostics/* as canonical namespace.',
            'Do not reintroduce temporary forbidden diagnostic endpoints.',
        ],
        'migration_order': [
            '1. Migrate frontend references from legacy routes to /api/receipt-diagnostics/*.',
            '2. Migrate local PowerShell/batch/tooling references.',
            '3. Keep legacy routes as compatibility wrappers for one validation cycle.',
            '4. Remove legacy route registrations after no references remain.',
        ],
        'canonical_files': canonical_files,
        'legacy_files': legacy_files,
        'frontend_legacy_files': frontend_legacy,
        'script_or_tooling_legacy_files': scripts_legacy,
        'backend_legacy_files': backend_legacy,
        'temporary_forbidden_files': forbidden_files,
        'safe_to_remove_after_migration': [
            'backend/app/api/receipt_diagnosis_routes.py',
            'backend/app/api/receipt_import_diagnosis_routes.py',
            'backend/app/api/receipt_kpi_routes.py',
        ],
        'not_safe_to_remove_now': [
            'Any legacy route still referenced by frontend, scripts, or docs in this inventory.',
            'Production /api/receipts/* routes.',
            'Preview /api/receipts/{receipt_table_id}/preview route.',
        ],
    }


def write_markdown(payload: dict) -> None:
    lines = []
    lines.append('# Receipt diagnostics dependency inventory')
    lines.append('')
    lines.append('Diagnostic-only inventory. No parser, status, database or UI changes.')
    lines.append('')
    summary = payload['summary']
    lines.append('## Summary')
    lines.append('')
    lines.append('| Metric | Count |')
    lines.append('|---|---:|')
    for key, value in summary.items():
        lines.append(f'| {key} | {value} |')
    lines.append('')
    lines.append('## Files with route dependencies')
    lines.append('')
    lines.append('| File | Area | Categories | Hits |')
    lines.append('|---|---|---|---:|')
    for file_path, info in sorted(payload['files'].items()):
        lines.append(f"| `{file_path}` | {info['area']} | {', '.join(info['categories'])} | {info['hit_count']} |")
    lines.append('')
    lines.append('## Detailed hits')
    lines.append('')
    for file_path, info in sorted(payload['files'].items()):
        lines.append(f"### `{file_path}`")
        for hit in info['hits']:
            lines.append(f"- L{hit['line']} `{hit['category']}` `{hit['match_type']}` `{hit['match']}` — {hit['snippet']}")
        lines.append('')
    lines.append('## Recommendations')
    lines.append('')
    rec = payload['recommendations']
    for section in ['safe_now', 'migration_order', 'safe_to_remove_after_migration', 'not_safe_to_remove_now']:
        lines.append(f'### {section}')
        for item in rec.get(section, []):
            lines.append(f'- {item}')
        lines.append('')
    MD_OUTPUT.write_text('\n'.join(lines), encoding='utf-8')


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = scan()
    JSON_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    write_markdown(payload)
    print(f'Inventory written to {JSON_OUTPUT}')
    print(f'Report written to {MD_OUTPUT}')
    print(json.dumps(payload['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
