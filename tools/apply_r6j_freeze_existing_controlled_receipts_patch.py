from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SSOT = ROOT / 'backend' / 'app' / 'services' / 'receipt_ssot_status.py'
BASELINE_V4 = ROOT / 'backend' / 'app' / 'services' / 'receipt_status_baseline_service_v4.py'

for target in [SSOT, BASELINE_V4]:
    content = target.read_text(encoding='utf-8-sig')
    target.with_suffix(target.suffix + '.bak-r6j').write_text(content, encoding='utf-8')

ssot = SSOT.read_text(encoding='utf-8-sig')

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
if new_status_code not in ssot:
    if old_status_code not in ssot:
        # tolerate files already partially patched; inject helpers after _status_code if needed
        if 'def _is_controlled_value(value: Any)' not in ssot:
            marker = 'def load_po_norm_status_items() -> dict[str, dict[str, Any]]:\n'
            if marker not in ssot:
                raise SystemExit('R6j aborted: cannot locate load_po_norm_status_items marker in SSOT file.')
            ssot = ssot.replace(marker, new_status_code + '\n' + marker, 1)
    else:
        ssot = ssot.replace(old_status_code, new_status_code, 1)

old_apply_block = '''    payload.pop("parse_status", None)
    payload.pop("actual_parse_status", None)
    payload.pop("actual_status_label", None)
    payload["po_norm_status"] = item["po_norm_status"]
    payload["po_norm_status_label"] = item["po_norm_status_label"]
    payload["po_norm_failed_criteria"] = item.get("po_norm_failed_criteria") or []
    payload["po_norm_reason"] = item.get("po_norm_reason")
    payload["inbox_status"] = item["po_norm_status_label"]
    payload["status"] = item["po_norm_status_label"]
'''
new_apply_block = '''    preserve_controlled = _has_existing_controlled_status(payload)
    if preserve_controlled:
        item = {
            **item,
            "po_norm_status": "controlled",
            "po_norm_status_label": "Gecontroleerd",
            "po_norm_failed_criteria": [],
            "po_norm_reason": "Gecontroleerd: bestaande gecontroleerde status behouden; Manual-retirement cleanup mag niet retroactief degraderen.",
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
if new_apply_block not in ssot:
    if old_apply_block not in ssot:
        raise SystemExit('R6j aborted: apply_po_norm_status output block not found.')
    ssot = ssot.replace(old_apply_block, new_apply_block, 1)

for forbidden in ['return "manual"', 'label == "Handmatig"']:
    ssot = ssot.replace('    if label == "Handmatig":\n        return "manual"\n', '')
    if forbidden in ssot:
        raise SystemExit(f'R6j guard failed: {forbidden!r} still present in receipt_ssot_status.py')
SSOT.write_text(ssot, encoding='utf-8')

baseline = BASELINE_V4.read_text(encoding='utf-8-sig')
# Keep status labels status-contract clean while still normalising old persisted manual values.
baseline = baseline.replace(
    "STATUS_LABELS = {'approved': 'Gecontroleerd', 'review_needed': 'Controle nodig', 'manual': 'Handmatig'}",
    "STATUS_LABELS = {'approved': 'Gecontroleerd', 'review_needed': 'Controle nodig', 'controlled': 'Gecontroleerd', 'manual': 'Controle nodig'}",
)

# Add a helper that identifies already-approved/controlled persisted receipts.
helper_marker = '''def _status_label(status: Any) -> str | None:
    if status is None:
        return None
    return STATUS_LABELS.get(str(status).strip(), str(status).strip())


'''
helper_insert = '''def _status_label(status: Any) -> str | None:
    if status is None:
        return None
    return STATUS_LABELS.get(str(status).strip(), str(status).strip())


def _is_existing_controlled_status(value: Any) -> bool:
    return str(value or '').strip().lower() in {'approved', 'controlled', 'gecontroleerd'}


'''
if '_is_existing_controlled_status' not in baseline:
    if helper_marker not in baseline:
        raise SystemExit('R6j aborted: baseline _status_label helper anchor not found.')
    baseline = baseline.replace(helper_marker, helper_insert, 1)

# Preserve existing controlled status in criteria calculation.
old_criteria = '''def _po_criteria(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    store_ok = _store_chain_match(expected, actual)
    total_ok = _amount_equals(actual.get('total_amount'), expected.get('total_amount'))
    count_ok = str(expected.get('line_count')) == str(actual.get('line_count'))
    sum_ok = _amount_equals(actual.get('net_line_sum_used_for_decision'), actual.get('total_amount'))
    failed = []
'''
new_criteria = '''def _po_criteria(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    if _is_existing_controlled_status(actual.get('parse_status')):
        return {
            'store_name_matches_baseline': True,
            'store_chain_matches_baseline': True,
            'expected_store_chain': normalize_store_chain(expected.get('store_chain') or expected.get('store_name')),
            'actual_store_chain': normalize_store_chain(actual.get('store_chain') or actual.get('store_name')),
            'total_amount_matches_baseline': True,
            'article_count_matches_baseline': True,
            'line_sum_matches_total': True,
            'all_criteria_pass': True,
            'failed_criteria': [],
            'po_norm_status': 'approved',
            'po_norm_status_label': _status_label('approved'),
            'preserved_existing_controlled_status': True,
        }

    store_ok = _store_chain_match(expected, actual)
    total_ok = _amount_equals(actual.get('total_amount'), expected.get('total_amount'))
    count_ok = str(expected.get('line_count')) == str(actual.get('line_count'))
    sum_ok = _amount_equals(actual.get('net_line_sum_used_for_decision'), actual.get('total_amount'))
    failed = []
'''
if 'preserved_existing_controlled_status' not in baseline:
    if old_criteria not in baseline:
        raise SystemExit('R6j aborted: _po_criteria anchor not found.')
    baseline = baseline.replace(old_criteria, new_criteria, 1)

BASELINE_V4.write_text(baseline, encoding='utf-8')

# Guards.
ssot_text = SSOT.read_text(encoding='utf-8')
for forbidden in ['return "manual"', 'label == "Handmatig"']:
    if forbidden in ssot_text:
        raise SystemExit(f'R6j guard failed: {forbidden!r} still present in SSOT')

baseline_text = BASELINE_V4.read_text(encoding='utf-8')
for required in ['_is_existing_controlled_status', 'preserved_existing_controlled_status']:
    if required not in baseline_text:
        raise SystemExit(f'R6j guard failed: {required!r} missing in baseline v4')

print('R6j freeze existing controlled receipts patch applied')
print('Updated:', SSOT)
print('Updated:', BASELINE_V4)
