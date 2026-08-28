from __future__ import annotations

import ast
from pathlib import Path
import re

ROOT = Path('backend/tests')
EXCLUDED = {ROOT / 'test_authorization_foundation_contract.py'}
IMPORT_LINE = 'from app.testing.authorization_schema_fixture import install_authorization_schema\n'
CALL_RE = re.compile(r'^(?P<indent>\s*)ensure_authorization_foundation\((?P<arg>[^\n]+)\)\s*$', re.MULTILINE)


def add_import(source: str, path: Path) -> str:
    if IMPORT_LINE.strip() in source:
        return source
    module = ast.parse(source, filename=str(path))
    body = list(module.body)
    insert_after = 0
    index = 0
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], 'value', None), ast.Constant) and isinstance(body[0].value.value, str):
        insert_after = body[0].end_lineno or body[0].lineno
        index = 1
    while index < len(body) and isinstance(body[index], (ast.Import, ast.ImportFrom)):
        insert_after = body[index].end_lineno or body[index].lineno
        index += 1
    lines = source.splitlines(keepends=True)
    lines.insert(insert_after, IMPORT_LINE)
    return ''.join(lines)


def patch_calls(source: str) -> tuple[str, int]:
    lines = source.splitlines()
    output: list[str] = []
    patched = 0
    for line in lines:
        match = re.match(r'^(?P<indent>\s*)ensure_authorization_foundation\((?P<arg>[^\n]+)\)\s*$', line)
        if match:
            installer = f"{match.group('indent')}install_authorization_schema({match.group('arg')})"
            previous = next((candidate for candidate in reversed(output) if candidate.strip()), '')
            if previous.strip() != installer.strip():
                output.append(installer)
                patched += 1
        output.append(line)
    suffix = '\n' if source.endswith('\n') else ''
    return '\n'.join(output) + suffix, patched


patched_files: list[str] = []
for path in sorted(ROOT.glob('test_*.py')):
    if path in EXCLUDED:
        continue
    source = path.read_text(encoding='utf-8')
    if 'ensure_authorization_foundation(' not in source:
        continue
    patched_source, call_count = patch_calls(source)
    if not call_count:
        continue
    patched_source = add_import(patched_source, path)
    path.write_text(patched_source, encoding='utf-8')
    patched_files.append(str(path))

if not patched_files:
    raise SystemExit('No authorization tests required fixture migration')

manifest = Path('/tmp/pr336_authorization_fixture_tests.txt')
manifest.write_text('\n'.join(patched_files) + '\n', encoding='utf-8')
print(f'PATCHED_AUTHORIZATION_TEST_FILES={len(patched_files)}')
for item in patched_files:
    print(item)
