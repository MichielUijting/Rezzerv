from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]

PRODUCTION_CHECK_PATHS = (
    ROOT / 'app' / 'services',
    ROOT / 'app' / 'receipt_ingestion',
)

FORBIDDEN_LITERALS = (
    'Jumbo foto 3.jpg',
    'jumbo_foto_3_manual_fallback',
    'Jumbo foto 1.jpeg',
    'Jumbo App 1.png',
    'Lidl App 1.png',
    'AH foto 1.pdf',
    'AH App 1.pdf',
    'plus foto 1.jpg',
    'plus foto 2.jpeg',
)

# Test/diagnostic modules may mention concrete filenames, but production parser
# areas must never branch on concrete receipt names. This guard only scans the
# production check paths above.
ALLOWLIST_FILES = {
    Path('app/testing/no_receipt_specific_parser_hardcoding_guard.py'),
}


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for check_path in PRODUCTION_CHECK_PATHS:
        if not check_path.exists():
            continue
        if check_path.is_file() and check_path.suffix == '.py':
            files.append(check_path)
            continue
        files.extend(sorted(path for path in check_path.rglob('*.py') if path.is_file()))
    return files


def _relative(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def _literal_pattern(literal: str) -> re.Pattern[str]:
    return re.compile(re.escape(literal), re.IGNORECASE)


def main() -> int:
    violations: list[str] = []
    patterns = tuple((literal, _literal_pattern(literal)) for literal in FORBIDDEN_LITERALS)

    for path in _iter_python_files():
        relative = _relative(path)
        if relative in ALLOWLIST_FILES:
            continue
        text = path.read_text(encoding='utf-8-sig')
        lines = text.splitlines()
        for literal, pattern in patterns:
            for match in pattern.finditer(text):
                line_no = text.count('\n', 0, match.start()) + 1
                line = lines[line_no - 1].strip() if 0 <= line_no - 1 < len(lines) else ''
                violations.append(f'{relative}:{line_no}: forbidden receipt-specific parser literal {literal!r}: {line}')

    if violations:
        print('NO-RECEIPT-SPECIFIC PARSER HARDCODING GUARD FAILED')
        for violation in violations:
            print(violation)
        return 1

    print('NO-RECEIPT-SPECIFIC PARSER HARDCODING GUARD PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
