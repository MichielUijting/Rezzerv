from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'backend' / 'app' / 'testing' / 'receipt_status_baseline' / 'expected_status_v6.json'
TEST = ROOT / 'backend' / 'tests' / 'test_manual_status_retired.py'

if BASELINE.exists():
    raw = BASELINE.read_text(encoding='utf-8-sig')
    BASELINE.with_suffix(BASELINE.suffix + '.bak-r6g').write_text(raw, encoding='utf-8')
    data = json.loads(raw)

    def migrate(value):
        if isinstance(value, dict):
            return {key: migrate('review_needed' if key == 'manual' else key) for key, value in value.items()}
        if isinstance(value, list):
            return [migrate(item) for item in value]
        if value == 'manual':
            return 'review_needed'
        if value == 'Handmatig':
            return 'Controle nodig'
        return value

    migrated = migrate(data)
    BASELINE.write_text(json.dumps(migrated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

TEST.write_text('''from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

STATUS_FILES = [
    ROOT / 'backend' / 'app' / 'services' / 'receipt_ssot_status.py',
    ROOT / 'backend' / 'app' / 'services' / 'receipt_status_baseline_service_v4.py',
    ROOT / 'backend' / 'app' / 'services' / 'receipt_parser_quality_patch.py',
    ROOT / 'backend' / 'app' / 'services' / 'receipt_status_sync.py',
    ROOT / 'backend' / 'app' / 'api' / 'receipt_import_diagnosis_routes.py',
    ROOT / 'backend' / 'app' / 'api' / 'receipt_ingestion_review_routes.py',
    ROOT / 'frontend' / 'src' / 'features' / 'receipts' / 'KassaPage.jsx',
]

BASELINE_FILES = [
    ROOT / 'backend' / 'app' / 'testing' / 'receipt_status_baseline' / 'expected_status_v6.json',
]

FORBIDDEN_STATUS_MARKERS = [
    "'manual'",
    '"manual"',
    'Handmatig',
    'manual_entry',
    'manual_entry_needed',
    'should_be_manual',
    'create_manual_receipt_when_parse_quality_low',
    'jumbo_foto_3_manual_fallback',
]


def test_manual_status_is_retired_from_active_receipt_lifecycle():
    offenders: list[str] = []
    for path in STATUS_FILES + BASELINE_FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding='utf-8-sig')
        for marker in FORBIDDEN_STATUS_MARKERS:
            if marker in text:
                offenders.append(f'{path.relative_to(ROOT)} contains {marker}')
    assert offenders == []
''', encoding='utf-8')

# Local guard for the patch itself.
for path in [BASELINE, TEST]:
    if not path.exists():
        continue
    text = path.read_text(encoding='utf-8-sig')
    if path == TEST:
        continue
    for forbidden in ['"manual"', '"Handmatig"']:
        if forbidden in text:
            raise SystemExit(f'R6g guard failed: {forbidden} still present in {path}')

print('R6g baseline/test guard patch applied')
if BASELINE.exists():
    print('Updated:', BASELINE)
print('Updated:', TEST)
