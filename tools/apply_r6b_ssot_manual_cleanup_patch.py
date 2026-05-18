from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGETS = {
    'baseline_v4': ROOT / 'backend' / 'app' / 'services' / 'receipt_status_baseline_service_v4.py',
    'ssot_status': ROOT / 'backend' / 'app' / 'services' / 'receipt_ssot_status.py',
}

for target in TARGETS.values():
    backup = target.with_suffix(target.suffix + '.bak-r6b')
    content = target.read_text(encoding='utf-8-sig')
    backup.write_text(content, encoding='utf-8')

    content = content.replace(
        "STATUS_LABELS = {'approved': 'Gecontroleerd', 'review_needed': 'Controle nodig', 'manual': 'Handmatig'}",
        "STATUS_LABELS = {'approved': 'Gecontroleerd', 'review_needed': 'Controle nodig'}",
    )

    content = content.replace(
        '    if label == "Handmatig":\n        return "manual"\n    return "review"',
        '    return "review"',
    )

    content = content.replace(
        'label = str(item.get(\'po_norm_status_label\') or \"Controle nodig\")',
        'label = str(item.get(\'po_norm_status_label\') or \"Controle nodig\")\n            if label == \"Handmatig\":\n                label = \"Controle nodig\"',
    )

    content = content.replace(
        '"po_norm_status": _status_code(label),',
        '"po_norm_status": \"review\" if label == \"Controle nodig\" else _status_code(label),',
    )

    target.write_text(content, encoding='utf-8')
    print(f'R6b patch applied to {target}')
