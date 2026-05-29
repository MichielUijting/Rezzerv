from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import inspect
import sys
from typing import Any

from sqlalchemy import text

from app.testing import no_monkeypatch_guard


@dataclass(frozen=True)
class FunctionSnapshot:
    name: str
    object_id: int
    module: str | None
    qualname: str | None
    source: str | None


@dataclass(frozen=True)
class ReceiptTarget:
    label: str
    path: str
    filename: str
    mime_type: str
    expected_line_count: int
    expected_total: float
    receipt_table_id: str | None = None


FUNCTION_NAMES = (
    'parse_receipt_content',
    '_parse_result_from_text_lines',
    '_store_from_text',
    '_total_amount_from_lines',
    '_extract_savings_action_lines',
    '_parse_store_specific_result',
)

TARGETS = (
    ReceiptTarget(
        label='AH App 1.pdf',
        path='/app/data/receipts/raw/1/2026/05/d02008189b7848df8d7248bc30494a09-AH App 1.pdf',
        filename='AH App 1.pdf',
        mime_type='application/pdf',
        expected_line_count=4,
        expected_total=5.02,
        receipt_table_id='9e5c77916acf4e6e871ad38f5516ebfb',
    ),
    ReceiptTarget(
        label='AH foto 1.pdf',
        path='/app/data/receipts/raw/1/2026/05/fac821f1c8b14148b7c55da145d2e6ca-AH foto 1.pdf',
        filename='AH foto 1.pdf',
        mime_type='application/pdf',
        expected_line_count=23,
        expected_total=49.27,
        receipt_table_id='a38b57f6a2c04aa39fb22c151b52c90e',
    ),
)


def _source(obj: Any) -> str | None:
    try:
        return inspect.getsourcefile(obj)
    except Exception:  # pragma: no cover - defensive diagnostic helper
        return None


def _snapshot(module: Any) -> dict[str, FunctionSnapshot]:
    snapshots: dict[str, FunctionSnapshot] = {}
    for name in FUNCTION_NAMES:
        obj = getattr(module, name)
        snapshots[name] = FunctionSnapshot(
            name=name,
            object_id=id(obj),
            module=getattr(obj, '__module__', None),
            qualname=getattr(obj, '__qualname__', None),
            source=_source(obj),
        )
    return snapshots


def _compare_snapshots(before: dict[str, FunctionSnapshot], after: dict[str, FunctionSnapshot]) -> list[str]:
    violations: list[str] = []
    for name in FUNCTION_NAMES:
        left = before[name]
        right = after[name]
        if left != right:
            violations.append(
                f'{name} changed after import app.main: before={left!r} after={right!r}'
            )
    return violations


def _assert_parse_result(result: Any, target: ReceiptTarget, phase: str) -> list[str]:
    violations: list[str] = []
    line_count = len(getattr(result, 'lines', []) or [])
    total = getattr(result, 'total_amount', None)
    if line_count != target.expected_line_count:
        violations.append(
            f'{phase} {target.label}: expected line_count={target.expected_line_count}, got {line_count}'
        )
    if total is None or abs(float(total) - float(target.expected_total)) > 0.005:
        violations.append(
            f'{phase} {target.label}: expected total={target.expected_total}, got {total}'
        )
    return violations


def _parse_targets(rs: Any, phase: str) -> list[str]:
    violations: list[str] = []
    for target in TARGETS:
        path = Path(target.path)
        if not path.exists():
            print(f'{phase} {target.label}: skipped; file not present at {target.path}')
            continue
        result = rs.parse_receipt_content(path.read_bytes(), target.filename, target.mime_type)
        line_count = len(getattr(result, 'lines', []) or [])
        total = getattr(result, 'total_amount', None)
        print(f'{phase} {target.label}: line_count={line_count} total={total}')
        violations.extend(_assert_parse_result(result, target, phase))
    return violations


def _check_database_targets(app_main: Any) -> list[str]:
    violations: list[str] = []
    if not hasattr(app_main, 'engine'):
        print('DB target check skipped; app.main has no engine')
        return violations

    with app_main.engine.begin() as conn:
        for target in TARGETS:
            if not target.receipt_table_id:
                continue
            row = conn.execute(
                text(
                    '''
                    SELECT id, line_count, total_amount
                    FROM receipt_tables
                    WHERE id = :id
                    LIMIT 1
                    '''
                ),
                {'id': target.receipt_table_id},
            ).mappings().first()
            if not row:
                print(f'DB {target.label}: skipped; receipt_table_id not present')
                continue
            line_count = row.get('line_count')
            total = row.get('total_amount')
            print(f'DB {target.label}: line_count={line_count} total={total}')
            if int(line_count or -1) != target.expected_line_count:
                violations.append(
                    f'DB {target.label}: expected line_count={target.expected_line_count}, got {line_count}'
                )
            if total is None or abs(float(total) - float(target.expected_total)) > 0.005:
                violations.append(
                    f'DB {target.label}: expected total={target.expected_total}, got {total}'
                )
    return violations


def main() -> int:
    print('R9-36N5 RELEASE QUALITY GATE')
    failures: list[str] = []

    print('\n[1/4] No-monkeypatch guard')
    guard_status = no_monkeypatch_guard.main()
    if guard_status != 0:
        failures.append('no_monkeypatch_guard failed')

    print('\n[2/4] Import side-effect check')
    import app.services.receipt_service as rs

    before = _snapshot(rs)
    failures.extend(_parse_targets(rs, 'BEFORE app.main'))

    import app.main as app_main

    after = _snapshot(rs)
    import_violations = _compare_snapshots(before, after)
    if import_violations:
        failures.extend(import_violations)
    else:
        print('Import side-effect check passed: core receipt functions unchanged')

    print('\n[3/4] AH PDF acceptance after app.main')
    failures.extend(_parse_targets(rs, 'AFTER app.main'))

    print('\n[4/4] Stored DB acceptance for AH PDF targets')
    failures.extend(_check_database_targets(app_main))

    if failures:
        print('\nR9-36N5 RELEASE QUALITY GATE FAILED')
        for failure in failures:
            print(f'- {failure}')
        return 1

    print('\nR9-36N5 RELEASE QUALITY GATE PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
