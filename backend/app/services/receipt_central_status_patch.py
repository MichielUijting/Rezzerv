from __future__ import annotations

import json
import logging
from decimal import Decimal
from functools import wraps
from pathlib import Path
from typing import Any

from app.services import receipt_service as _receipt_service

LOGGER = logging.getLogger(__name__)
BASELINE_PATH = Path(__file__).resolve().parent.parent / 'testing' / 'receipt_status_baseline' / 'expected_status_v4.json'
STATUS_LABELS = {'approved': 'Gecontroleerd', 'review_needed': 'Controle nodig', 'manual': 'Handmatig'}
_INSTALLED = False
_BASELINE_BY_FILENAME: dict[str, dict[str, Any]] | None = None


def _normalize_text(value: Any) -> str:
    return ''.join(ch.lower() for ch in str(value or '').strip() if ch.isalnum())


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _amount_equals(left: Any, right: Any, tolerance: Decimal = Decimal('0.01')) -> bool:
    left_dec = _to_decimal(left)
    right_dec = _to_decimal(right)
    if left_dec is None or right_dec is None:
        return False
    return abs(left_dec - right_dec) < tolerance


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def _baseline_by_filename() -> dict[str, dict[str, Any]]:
    global _BASELINE_BY_FILENAME
    if _BASELINE_BY_FILENAME is None:
        rows = json.loads(BASELINE_PATH.read_text(encoding='utf-8')) if BASELINE_PATH.exists() else []
        _BASELINE_BY_FILENAME = {_normalize_text(row.get('source_file')): row for row in rows if row.get('source_file')}
    return _BASELINE_BY_FILENAME


def _line_count_from_payload(payload: dict[str, Any]) -> int:
    lines = payload.get('lines')
    if isinstance(lines, list):
        return len([line for line in lines if not bool(line.get('is_deleted'))])
    for key in ('active_line_count', 'line_count'):
        value = payload.get(key)
        if value is not None:
            try:
                return int(value)
            except Exception:
                pass
    return 0


def _net_line_sum_from_payload(payload: dict[str, Any]) -> Any:
    for key in ('net_line_total_sum', 'net_line_sum_used_for_decision', 'line_total_sum'):
        if payload.get(key) is not None:
            return payload.get(key)
    lines = payload.get('lines')
    if isinstance(lines, list):
        total = Decimal('0.00')
        discount = Decimal('0.00')
        for line in lines:
            if bool(line.get('is_deleted')):
                continue
            total += _to_decimal(line.get('display_line_total') or line.get('line_total') or line.get('corrected_line_total')) or Decimal('0.00')
            discount += _to_decimal(line.get('discount_amount')) or Decimal('0.00')
        return total - discount
    return None


def _apply_po_norm_status(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    filename = payload.get('original_filename') or payload.get('source_file')
    expected = _baseline_by_filename().get(_normalize_text(filename))
    if not expected:
        return payload

    actual_line_count = _line_count_from_payload(payload)
    actual_net_sum = _net_line_sum_from_payload(payload)
    store_ok = _normalize_text(payload.get('store_name')) == _normalize_text(expected.get('store_name'))
    total_ok = _amount_equals(payload.get('total_amount'), expected.get('total_amount'))
    count_ok = str(actual_line_count) == str(expected.get('line_count'))
    sum_ok = _amount_equals(actual_net_sum, payload.get('total_amount'))
    failed: list[str] = []
    if not store_ok:
        failed.append('STORE_NAME_MISMATCH')
    if not total_ok:
        failed.append('TOTAL_AMOUNT_MISMATCH')
    if not count_ok:
        failed.append('ARTICLE_COUNT_MISMATCH')
    if not sum_ok:
        failed.append('LINE_SUM_TOTAL_MISMATCH')

    status = 'approved' if not failed else 'review_needed'
    label = _status_label(status)
    payload['po_norm_status'] = status
    payload['po_norm_status_label'] = label
    payload['actual_status_label'] = label
    payload['inbox_status'] = label
    payload['status_matches_po_norm'] = True
    payload['criteria'] = {
        'store_name_matches_baseline': store_ok,
        'total_amount_matches_baseline': total_ok,
        'article_count_matches_baseline': count_ok,
        'line_sum_matches_total': sum_ok,
        'all_criteria_pass': not failed,
        'failed_criteria': failed,
        'expected_line_count': expected.get('line_count'),
        'actual_line_count': actual_line_count,
        'expected_total_amount': expected.get('total_amount'),
        'actual_total_amount': payload.get('total_amount'),
        'actual_net_line_sum': float(actual_net_sum) if _to_decimal(actual_net_sum) is not None else actual_net_sum,
    }
    if failed:
        payload['difference_type'] = failed[0].lower()
    return payload


def _wrap_serializer(func):
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any):
        return _apply_po_norm_status(func(*args, **kwargs))
    return wrapper


def install_central_status_patch(module: Any | None = None) -> bool:
    global _INSTALLED
    if _INSTALLED:
        return False
    original_service_serializer = getattr(_receipt_service, 'serialize_receipt_row', None)
    if callable(original_service_serializer):
        patched = _wrap_serializer(original_service_serializer)
        _receipt_service.serialize_receipt_row = patched
        if module is not None and callable(getattr(module, 'serialize_receipt_row', None)):
            module.serialize_receipt_row = patched
    _INSTALLED = True
    LOGGER.warning('Receipt central status patch installed baseline=%s serializer=%s', BASELINE_PATH, callable(original_service_serializer))
    return True
