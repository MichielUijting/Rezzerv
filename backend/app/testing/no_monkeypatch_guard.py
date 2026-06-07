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
import re
import sys

ROOT = Path(__file__).resolve().parents[2]

CHECK_PATHS = [
    ROOT / 'sitecustomize.py',
    ROOT / 'app' / 'services',
]

FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        'assignment to receipt_service runtime',
        re.compile(r'\b_receipt_service\.[A-Za-z_][A-Za-z0-9_]*\s='),
    ),
    (
        'assignment to FastAPI route internals',
        re.compile(r'\bAPIRoute\.get_route_handler\s='),
    ),
    (
        'assignment to parser patch helper module qpatch',
        re.compile(r'\bqpatch\.[A-Za-z_][A-Za-z0-9_]*\s='),
    ),
    (
        'assignment to loyalty patch helper module',
        re.compile(r'\bloyalty\.[A-Za-z_][A-Za-z0-9_]*\s='),
    ),
    (
        'module-level patch install call',
        re.compile(r'^\s*install_[A-Za-z0-9_]*patch\s*\(', re.MULTILINE),
    ),
    (
        'sitecustomize imports app patch modules',
        re.compile(r'from\s+app\.services\s+import\s+.*patch'),
    ),
)

ALLOWLIST_FILES = {
    # This guard describes forbidden patterns in strings, so it must be excluded.
    Path('app/testing/no_monkeypatch_guard.py'),
}


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for check_path in CHECK_PATHS:
        if not check_path.exists():
            continue
        if check_path.is_file():
            files.append(check_path)
        else:
            files.extend(sorted(check_path.rglob('*.py')))
    return files


def rel(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def main() -> int:
    violations: list[str] = []
    for path in iter_python_files():
        relative = rel(path)
        if relative in ALLOWLIST_FILES:
            continue
        text = path.read_text(encoding='utf-8-sig')
        for label, pattern in FORBIDDEN_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text.count('\n', 0, match.start()) + 1
                line = text.splitlines()[line_no - 1].strip()
                violations.append(f'{relative}:{line_no}: {label}: {line}')

    if violations:
        print('NO-MONKEYPATCH GUARD FAILED')
        for violation in violations:
            print(violation)
        return 1

    print('NO-MONKEYPATCH GUARD PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
