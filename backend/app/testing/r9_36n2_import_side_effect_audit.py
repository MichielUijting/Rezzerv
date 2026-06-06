"""
Technical Design Reference:
- TD Section: TD-08 Test, baseline en regressie
- Module Role: Test or baseline support
- Runtime Type: test
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

from pathlib import Path
import inspect
import sys
from typing import Any

from sqlalchemy import text

import app.services.receipt_service as rs


def describe(name: str, obj: Any) -> None:
    try:
        source_file = inspect.getsourcefile(obj)
    except Exception as exc:  # pragma: no cover - diagnostic only
        source_file = f'<source_error {exc}>'
    print(f'{name}:')
    print(f'  id={id(obj)}')
    print(f'  module={getattr(obj, "__module__", None)}')
    print(f'  qualname={getattr(obj, "__qualname__", None)}')
    print(f'  source={source_file}')


def parse_target(label: str, path: str, filename: str, mime_type: str):
    result = rs.parse_receipt_content(Path(path).read_bytes(), filename, mime_type)
    print(f'{label}: line_count={len(result.lines)} total={result.total_amount} store={result.store_name}')
    for index, line in enumerate(result.lines):
        raw = str(line.get('raw_label') or '')
        norm = str(line.get('normalized_label') or '')
        haystack = f'{raw} {norm}'.upper()
        if 'KOOP' in haystack or 'ZEGEL' in haystack or 'PREMIUM' in haystack:
            print(f'  SAVINGS_LINE {index}: raw={raw} norm={norm} total={line.get("line_total")}')
    return result


def describe_receipt_functions(stage: str) -> None:
    print()
    print(f'=== {stage} ===')
    describe('rs.parse_receipt_content', rs.parse_receipt_content)
    describe('rs._parse_result_from_text_lines', rs._parse_result_from_text_lines)
    describe('rs._store_from_text', rs._store_from_text)
    describe('rs._total_amount_from_lines', rs._total_amount_from_lines)
    describe('rs._extract_savings_action_lines', rs._extract_savings_action_lines)
    describe('rs._parse_store_specific_result', rs._parse_store_specific_result)


def main() -> None:
    targets = [
        (
            'AH App 1 hardcoded',
            '/app/data/receipts/raw/1/2026/05/d02008189b7848df8d7248bc30494a09-AH App 1.pdf',
            'AH App 1.pdf',
            'application/pdf',
        ),
        (
            'AH foto 1 hardcoded',
            '/app/data/receipts/raw/1/2026/05/fac821f1c8b14148b7c55da145d2e6ca-AH foto 1.pdf',
            'AH foto 1.pdf',
            'application/pdf',
        ),
    ]

    describe_receipt_functions('BEFORE app.main')
    for label, path, filename, mime_type in targets:
        print()
        parse_target('BEFORE ' + label, path, filename, mime_type)

    print()
    print('=== IMPORT app.main ===')
    import app.main as app_main
    print('main imported')

    describe_receipt_functions('AFTER app.main')

    print()
    print('=== LOADED PATCH MODULES ===')
    for module_name in sorted(sys.modules):
        if 'receipt' in module_name and ('patch' in module_name or 'debug' in module_name or 'diagnos' in module_name):
            print(module_name)

    for label, path, filename, mime_type in targets:
        print()
        parse_target('AFTER ' + label, path, filename, mime_type)

    print()
    print('=== DB STORAGE PATHS FOR TARGET IDS ===')
    receipt_table_ids = [
        '9e5c77916acf4e6e871ad38f5516ebfb',
        'a38b57f6a2c04aa39fb22c151b52c90e',
    ]
    with app_main.engine.begin() as conn:
        for receipt_table_id in receipt_table_ids:
            row = conn.execute(
                text(
                    '''
                    SELECT
                        rt.id AS receipt_table_id,
                        rt.line_count,
                        rt.total_amount,
                        rr.original_filename,
                        rr.mime_type,
                        rr.storage_path,
                        rr.id AS raw_receipt_id
                    FROM receipt_tables rt
                    JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
                    WHERE rt.id = :id
                    LIMIT 1
                    '''
                ),
                {'id': receipt_table_id},
            ).mappings().first()
            print(dict(row or {}))
            if row:
                result = rs.parse_receipt_content(
                    Path(row['storage_path']).read_bytes(),
                    row['original_filename'],
                    row['mime_type'],
                )
                print(
                    'DB_PATH_PARSE',
                    receipt_table_id,
                    'line_count=', len(result.lines),
                    'total=', result.total_amount,
                    'path=', row['storage_path'],
                )


if __name__ == '__main__':
    main()
