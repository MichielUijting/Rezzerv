from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r7b12')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

import_line = 'from app.receipt_ingestion.normalization import normalize_text_lines\n'
if import_line not in content:
    anchor = 'from app.receipt_ingestion.generic_text_parser import route_generic_text_parser\n'
    fallback_anchor = 'from app.receipt_ingestion.parser_debug_serializer import build_parser_debug_payload\n'
    if anchor in content:
        content = content.replace(anchor, anchor + import_line, 1)
    elif fallback_anchor in content:
        content = content.replace(fallback_anchor, fallback_anchor + import_line, 1)
    else:
        raise SystemExit('R7b-12 aborted: no safe receipt_ingestion import anchor found.')

# Replace all calls first so the public behavior remains identical through the imported helper.
content = content.replace('_normalize_text_lines(', 'normalize_text_lines(')

# Remove the former local helper implementation if present.
pattern = re.compile(
    r"\n\ndef normalize_text_lines\(text: str\) -> list\[str\]:\n"
    r"\s+raw_lines = re\.split\(r'\\r\?\\n\+', text\)\n"
    r"\s+lines: list\[str\] = \[\]\n"
    r"\s+for line in raw_lines:\n"
    r"\s+normalized = re\.sub\(r'\\s\+', ' ', line\)\.strip\(\)\n"
    r"\s+if normalized:\n"
    r"\s+lines\.append\(normalized\)\n"
    r"\s+return lines\n",
    re.MULTILINE,
)
content, removed = pattern.subn('\n', content, count=1)

# If the local helper used the old name and did not get renamed by replacement, remove that too.
pattern_old = re.compile(
    r"\n\ndef _normalize_text_lines\(text: str\) -> list\[str\]:\n"
    r"\s+raw_lines = re\.split\(r'\\r\?\\n\+', text\)\n"
    r"\s+lines: list\[str\] = \[\]\n"
    r"\s+for line in raw_lines:\n"
    r"\s+normalized = re\.sub\(r'\\s\+', ' ', line\)\.strip\(\)\n"
    r"\s+if normalized:\n"
    r"\s+lines\.append\(normalized\)\n"
    r"\s+return lines\n",
    re.MULTILINE,
)
content, removed_old = pattern_old.subn('\n', content, count=1)

if removed + removed_old == 0:
    raise SystemExit('R7b-12 aborted: local normalize text lines helper block not found.')

# Guards: no old helper name, no local duplicate definition.
if '_normalize_text_lines(' in content:
    raise SystemExit('R7b-12 guard failed: _normalize_text_lines call still present.')
if 'def normalize_text_lines(text: str) -> list[str]:' in content:
    raise SystemExit('R7b-12 guard failed: local normalize_text_lines definition still present in receipt_service.py.')
if import_line not in content:
    raise SystemExit('R7b-12 guard failed: normalization import missing.')

TARGET.write_text(content, encoding='utf-8')
print('R7b-12 normalization helper wiring applied to', TARGET)
print('Backup written to', BACKUP)
