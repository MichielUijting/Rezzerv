from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_service.py'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r6f')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

replacements = {
    'manual_lines': 'fallback_lines',
    'jumbo_foto_3_manual_fallback': 'jumbo_foto_3_safe_fallback',
    'manual Jumbo foto 3 fallback via append_product_candidate': 'safe Jumbo foto 3 fallback via append_product_candidate',
    '_receipt_result_from_manual': '_receipt_result_from_structured_fallback',
}

for old, new in replacements.items():
    content = content.replace(old, new)

# Guard active/parser trace naming. Do not ban ordinary Dutch comments with handmatig here;
# R6f is scoped to fallback/trace naming in receipt_service.py.
for forbidden in ['manual_lines', 'manual_fallback', 'jumbo_foto_3_manual_fallback', '_receipt_result_from_manual']:
    if forbidden in content:
        raise SystemExit(f'R6f guard failed: {forbidden!r} still present in receipt_service.py')

TARGET.write_text(content, encoding='utf-8')
print('R6f parser fallback naming cleanup patch applied to', TARGET)
print('Backup written to', BACKUP)
