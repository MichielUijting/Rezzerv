from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'

content = TARGET.read_text(encoding='utf-8-sig')
backup = TARGET.with_suffix('.py.bak-r7b2')
backup.write_text(content, encoding='utf-8')

if '_line_dict(' not in content:
    raise SystemExit('R7b-2 aborted: _line_dict helper already absent.')

# Guard: helper must no longer be referenced outside its own definition.
occurrences = [m.start() for m in re.finditer(r'_line_dict\(', content)]
if len(occurrences) != 1:
    raise SystemExit(f'R7b-2 aborted: expected exactly one _line_dict occurrence, found {len(occurrences)}.')

pattern = re.compile(
    r"\n\ndef _line_dict\(.*?\n\s*}\n",
    re.DOTALL,
)
match = pattern.search(content)
if not match:
    raise SystemExit('R7b-2 aborted: _line_dict function block not found.')

content = content[:match.start()] + '\n\n' + content[match.end():]

# Maintenance note near structured helper.
anchor = 'def _receipt_result_from_manual('
if anchor not in content:
    raise SystemExit('R7b-2 aborted: structured result helper anchor missing.')

note = '# R7b-2: legacy _line_dict helper removed; gateways are now the canonical product-shape path.\n\n'
content = content.replace(anchor, note + anchor, 1)

TARGET.write_text(content, encoding='utf-8')

final_content = TARGET.read_text(encoding='utf-8')
if '_line_dict(' in final_content:
    raise SystemExit('R7b-2 guard failed: _line_dict helper still present.')

print('R7b-2 patch applied successfully.')
print('Updated:', TARGET)
