from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'services' / 'receipt_ssot_status.py'
BACKUP = TARGET.with_suffix(TARGET.suffix + '.bak-r6i')

content = TARGET.read_text(encoding='utf-8-sig')
BACKUP.write_text(content, encoding='utf-8')

old_status_code = '''def _status_code(label: str) -> str:
    if label == "Gecontroleerd":
        return "controlled"
    if label == "Handmatig":
        return "manual"
    return "review"
'''
new_status_code = '''def _status_code(label: str) -> str:
    if label == "Gecontroleerd":
        return "controlled"
    return "review"


def _is_controlled_value(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"gecontroleerd", "approved", "controlled"}


def _has_existing_controlled_status(payload: dict[str, Any]) -> bool:
    return any(
        _is_controlled_value(payload.get(key))
        for key in ("status", "inbox_status", "po_norm_status", "po_norm_status_label", "parse_status")
    )
'''
if new_status_code not in content:
    if old_status_code not in content:
        raise SystemExit('R6i patch aborted: _status_code block not found.')
    content = content.replace(old_status_code, new_status_code, 1)

old_item_block = '''    payload.pop("parse_status", None)
    payload.pop("actual_parse_status", None)
    payload.pop("actual_status_label", None)
    payload["po_norm_status"] = item["po_norm_status"]
    payload["po_norm_status_label"] = item["po_norm_status_label"]
    payload["po_norm_failed_criteria"] = item.get("po_norm_failed_criteria") or []
    payload["po_norm_reason"] = item.get("po_norm_reason")
    payload["inbox_status"] = item["po_norm_status_label"]
    payload["status"] = item["po_norm_status_label"]
'''
new_item_block = '''    preserve_controlled = _has_existing_controlled_status(payload)
    if preserve_controlled:
        item = {
            **item,
            "po_norm_status": "controlled",
            "po_norm_status_label": "Gecontroleerd",
            "po_norm_reason": item.get("po_norm_reason") or "Gecontroleerd: bestaande gecontroleerde status behouden tijdens Manual-retirement cleanup.",
        }

    payload.pop("parse_status", None)
    payload.pop("actual_parse_status", None)
    payload.pop("actual_status_label", None)
    payload["po_norm_status"] = item["po_norm_status"]
    payload["po_norm_status_label"] = item["po_norm_status_label"]
    payload["po_norm_failed_criteria"] = item.get("po_norm_failed_criteria") or []
    payload["po_norm_reason"] = item.get("po_norm_reason")
    payload["inbox_status"] = item["po_norm_status_label"]
    payload["status"] = item["po_norm_status_label"]
'''
if new_item_block not in content:
    if old_item_block not in content:
        raise SystemExit('R6i patch aborted: apply_po_norm_status item block not found.')
    content = content.replace(old_item_block, new_item_block, 1)

for forbidden in ['return "manual"', 'label == "Handmatig"']:
    if forbidden in content:
        raise SystemExit(f'R6i guard failed: {forbidden!r} still present in receipt_ssot_status.py')

TARGET.write_text(content, encoding='utf-8')
print('R6i controlled status preservation patch applied to', TARGET)
print('Backup written to', BACKUP)
