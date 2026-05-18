from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r7b3')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

old_name = '_receipt_result_from_manual'
new_name = '_receipt_result_from_structured_source'

if old_name not in content:
    raise SystemExit(f'R7b-3 aborted: {old_name} not found; patch may already be applied.')

content = content.replace(old_name, new_name)

# Add/normalize short maintenance note next to renamed helper.
anchor = f'def {new_name}('
note = '# R7b-3: status-neutral result builder for structured PDF/e-mail/store-specific parsers.\n'
if anchor not in content:
    raise SystemExit(f'R7b-3 aborted: renamed helper anchor {anchor!r} not found.')
if note not in content:
    content = content.replace(anchor, note + anchor, 1)

if old_name in content:
    raise SystemExit(f'R7b-3 guard failed: {old_name} still present after rename.')

TARGET.write_text(content, encoding='utf-8')
print('R7b-3 structured result builder rename applied to', TARGET)
print('Backup written to', BACKUP)
