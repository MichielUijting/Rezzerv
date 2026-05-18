from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'api' / 'receipt_ingestion_review_routes.py'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r6e')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

replacements = {
    "'manual_entry_needed'": "'review_input_needed'",
    "action == 'manual_entry'": "action == 'correct_in_review'",
    "return 'manual_entry_needed'": "return 'review_input_needed'",
    "'manual_entry_needed'": "'review_input_needed'",
    "'recommended_user_action': 'manual_entry' if readiness == 'manual_entry_needed' else '-'": "'recommended_user_action': 'correct_in_review' if readiness == 'review_input_needed' else '-'",
}

for old, new in replacements.items():
    content = content.replace(old, new)

# Extra explicit replacements after broad label replacement.
content = content.replace("readiness == 'manual_entry_needed'", "readiness == 'review_input_needed'")
content = content.replace("'manual_entry'", "'correct_in_review'")
content = content.replace('manual_entry', 'correct_in_review')
content = content.replace('manual_entry_needed', 'review_input_needed')

for forbidden in ['manual_entry_needed', 'manual_entry']:
    if forbidden in content:
        raise SystemExit(f'R6e guard failed: {forbidden!r} still present in review readiness route.')

TARGET.write_text(content, encoding='utf-8')
print('R6e review readiness manual cleanup patch applied to', TARGET)
print('Backup written to', BACKUP)
