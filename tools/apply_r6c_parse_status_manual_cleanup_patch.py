from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / 'backend' / 'app' / 'services' / 'receipt_parser_quality_patch.py',
    ROOT / 'backend' / 'app' / 'services' / 'receipt_status_sync.py',
]

for target in TARGETS:
    content = target.read_text(encoding='utf-8-sig')
    target.with_suffix(target.suffix + '.bak-r6c').write_text(content, encoding='utf-8')

    if target.name == 'receipt_parser_quality_patch.py':
        content = content.replace(
            "        result.parse_status = 'manual'\n",
            "        result.parse_status = 'review_needed'\n",
        )

    if target.name == 'receipt_status_sync.py':
        content = content.replace(
            "return 'manual'",
            "return 'review_needed'",
        )
        content = content.replace(
            "counts = {'checked': 0, 'updated': 0, 'approved': 0, 'review_needed': 0, 'manual': 0}",
            "counts = {'checked': 0, 'updated': 0, 'approved': 0, 'review_needed': 0}",
        )
        content = content.replace(
            "counts[status] = counts.get(status, 0) + 1",
            "if status == 'manual':\n                status = 'review_needed'\n            counts[status] = counts.get(status, 0) + 1",
        )

    target.write_text(content, encoding='utf-8')
    print(f'R6c patch applied to {target}')

# Guard: new parse/quality/sync code should no longer emit manual status.
for target in TARGETS:
    content = target.read_text(encoding='utf-8')
    forbidden = ["parse_status = 'manual'", 'return \'manual\'', '"manual"']
    if target.name == 'receipt_status_sync.py':
        forbidden = ["return 'manual'", "'manual': 0"]
    for marker in forbidden:
        if marker in content:
            raise SystemExit(f'R6c guard failed: {marker!r} still present in {target}')
