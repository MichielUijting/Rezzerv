from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

TARGETS = ('"demo-household"', "'demo-household'", '"1"', "'1'")
TEXT_SUFFIXES = {'.py', '.js', '.jsx', '.ts', '.tsx', '.json', '.yml', '.yaml', '.md', '.sql', '.txt'}
EXCLUDED_PARTS = {'.git', 'node_modules', 'dist', 'build', '__pycache__', '.venv', 'venv'}


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


def audit(root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, 1):
            matched = [target for target in TARGETS if target in line]
            if not matched:
                continue
            rows.append({
                'path': rel.as_posix(),
                'line': number,
                'classification': classify(rel),
                'targets': matched,
                'source': line.strip(),
                'previous': lines[number - 2].strip() if number > 1 else '',
                'next': lines[number].strip() if number < len(lines) else '',
            })
    summary: dict[str, int] = {}
    for row in rows:
        summary[row['classification']] = summary.get(row['classification'], 0) + 1
    return {
        'audit_version': 1,
        'targets': list(TARGETS),
        'summary': {'occurrences': len(rows), 'by_classification': summary},
        'occurrences': rows,
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
