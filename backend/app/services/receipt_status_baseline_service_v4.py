from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import get_runtime_datastore_info

BASELINE_DIR = Path(__file__).resolve().parent.parent / 'testing' / 'receipt_status_baseline'
EXPECTED_STATUS_PATH = BASELINE_DIR / 'expected_status_v4.json'
CRITERIA_DOC_PATH = BASELINE_DIR / 'Categorie_kassabon_v1.1.docx'

STATUS_LABELS = {'approved': 'Gecontroleerd', 'review_needed': 'Controle nodig', 'manual': 'Handmatig'}


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    dec = _to_decimal(value)
    return float(dec) if dec is not None else None


def _amount_equals(left: Any, right: Any, tolerance: Decimal = Decimal('0.01')) -> bool:
    left_dec = _to_decimal(left)
    right_dec = _to_decimal(right)
    if left_dec is None or right_dec is None:
        return False
    return abs(left_dec - right_dec) < tolerance


def _status_label(status: Any) -> str | None:
    if status is None:
        return None
    return STATUS_LABELS.get(str(status).strip(), str(status).strip())


def _normalize_text(value: Any) -> str:
    return ''.join(ch.lower() for ch in str(value or '').strip() if ch.isalnum())


def _column_names(conn, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(text(f'PRAGMA table_info({table_name})')).fetchall()}


def _actual_line_columns(conn) -> dict[str, str]:
    cols = _column_names(conn, 'receipt_table_lines')
    return {'line_total': 'COALESCE(rtl.corrected_line_total, rtl.line_total)' if 'corrected_line_total' in cols else 'rtl.line_total'}


def load_expected_receipt_statuses() -> list[dict[str, Any]]:
    return json.loads(EXPECTED_STATUS_PATH.read_text(encoding='utf-8'))


def load_baseline_receipts() -> list[dict[str, Any]]:
    return []


def load_baseline_receipt_lines() -> list[dict[str, Any]]:
    return []


def _active_baseline_scope(expected_rows: list[dict[str, Any]], actual_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active_files = {_normalize_text(row.get('original_filename')) for row in actual_rows if row.get('original_filename')}
    if not active_files:
        return expected_rows
    scoped = [row for row in expected_rows if _normalize_text(row.get('source_file')) in active_files]
    return scoped or expected_rows


def _actual_status_inputs(conn, receipt_table_id: str) -> dict[str, Any]:
    expr = _actual_line_columns(conn)
    row = conn.execute(text(f'''
        SELECT rt.id AS receipt_table_id, rt.raw_receipt_id, rt.household_id, rt.store_name,
               rt.total_amount, rt.discount_total, rt.line_count, rt.parse_status, rt.deleted_at,
               rt.totals_overridden, rr.original_filename,
               COALESCE(SUM(CASE WHEN COALESCE(rtl.is_deleted, 0) = 0 THEN COALESCE({expr['line_total']}, 0) ELSE 0 END), 0) AS actual_line_sum,
               SUM(CASE WHEN COALESCE(rtl.is_deleted, 0) = 0 THEN 1 ELSE 0 END) AS active_line_count
        FROM receipt_tables rt
        JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
        LEFT JOIN receipt_table_lines rtl ON rtl.receipt_table_id = rt.id
        WHERE rt.id = :receipt_table_id
        GROUP BY rt.id, rt.raw_receipt_id, rt.household_id, rt.store_name, rt.total_amount, rt.discount_total,
                 rt.line_count, rt.parse_status, rt.deleted_at, rt.totals_overridden, rr.original_filename
        LIMIT 1
    '''), {'receipt_table_id': receipt_table_id}).mappings().first()
    if not row:
        return {}
    data = dict(row)
    discount_total = _to_decimal(data.get('discount_total')) or Decimal('0')
    actual_line_sum = _to_decimal(data.get('actual_line_sum')) or Decimal('0')
    data.update({
        'active_line_count': int(data.get('active_line_count') or 0),
        'sum_line_total_used_for_decision': float(actual_line_sum),
        'discount_total_used_for_decision': float(discount_total),
        'net_line_sum_used_for_decision': float(actual_line_sum + discount_total),
    })
    return data


def _score_actual_match(expected: dict[str, Any], actual: dict[str, Any]) -> tuple[int, dict[str, bool], str]:
    flags = {'filename_exact': False, 'store_match': False, 'total_match': False, 'line_count_match': False}
    score = 0
    reasons = []
    if _normalize_text(expected.get('source_file')) == _normalize_text(actual.get('original_filename')):
        score += 100
        flags['filename_exact'] = True
        reasons.append('bestandsnaam exact')
    if _normalize_text(expected.get('store_name')) == _normalize_text(actual.get('store_name')):
        score += 30
        flags['store_match'] = True
        reasons.append('winkelnaam exact genormaliseerd')
    if _amount_equals(expected.get('total_amount'), actual.get('total_amount')):
        score += 20
        flags['total_match'] = True
        reasons.append('totaalbedrag komt overeen')
    if str(expected.get('line_count')) == str(actual.get('line_count')):
        score += 10
        flags['line_count_match'] = True
        reasons.append('artikelcount komt overeen')
    return score, flags, '; '.join(reasons)


def _po_criteria(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    store_ok = _normalize_text(expected.get('store_name')) == _normalize_text(actual.get('store_name'))
    total_ok = _amount_equals(actual.get('total_amount'), expected.get('total_amount'))
    count_ok = str(expected.get('line_count')) == str(actual.get('line_count'))
    sum_ok = _amount_equals(actual.get('net_line_sum_used_for_decision'), actual.get('total_amount'))
    failed = []
    if not store_ok:
        failed.append('STORE_NAME_MISMATCH')
    if not total_ok:
        failed.append('TOTAL_AMOUNT_MISMATCH')
    if not count_ok:
        failed.append('ARTICLE_COUNT_MISMATCH')
    if not sum_ok:
        failed.append('LINE_SUM_TOTAL_MISMATCH')
    all_ok = store_ok and total_ok and count_ok and sum_ok
    return {'store_name_matches_baseline': store_ok, 'total_amount_matches_baseline': total_ok, 'article_count_matches_baseline': count_ok, 'line_sum_matches_total': sum_ok, 'all_criteria_pass': all_ok, 'failed_criteria': failed, 'po_norm_status': 'approved' if all_ok else 'review_needed', 'po_norm_status_label': _status_label('approved' if all_ok else 'review_needed')}


def _reason(criteria: dict[str, Any]) -> str:
    if criteria['all_criteria_pass']:
        return 'Gecontroleerd: winkelnaam, totaalbedrag, artikelcount en regelsom voldoen aan de PO-norm.'
    labels = {'STORE_NAME_MISMATCH': 'winkelnaam wijkt af van baseline', 'TOTAL_AMOUNT_MISMATCH': 'totaalbedrag wijkt af van baseline', 'ARTICLE_COUNT_MISMATCH': 'artikelcount wijkt af van baseline', 'LINE_SUM_TOTAL_MISMATCH': 'som van artikelregels sluit niet aan op kassabontotaal'}
    return 'Controle nodig: ' + '; '.join(labels.get(code, code) for code in criteria['failed_criteria'])


def _fetch_archived_receipt_scope(conn, household_id: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    sql = '''SELECT rt.id AS receipt_table_id, rr.original_filename, rt.store_name, rt.purchase_at, rt.total_amount, rt.parse_status, rt.line_count, rt.deleted_at FROM receipt_tables rt JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id WHERE rt.deleted_at IS NOT NULL'''
    if household_id is not None:
        sql += ' AND rt.household_id = :household_id'
        params['household_id'] = str(household_id)
    sql += ' ORDER BY rt.deleted_at DESC, rt.created_at DESC'
    return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]


def validate_receipt_status_baseline(conn, household_id: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    sql = '''SELECT rt.id AS receipt_table_id FROM receipt_tables rt JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id WHERE rt.deleted_at IS NULL'''
    if household_id is not None:
        sql += ' AND rt.household_id = :household_id'
        params['household_id'] = str(household_id)
    actual_rows = []
    for row in conn.execute(text(sql), params).mappings().all():
        inputs = _actual_status_inputs(conn, str(row['receipt_table_id']))
        if inputs:
            actual_rows.append(inputs)
    expected_rows = _active_baseline_scope(load_expected_receipt_statuses(), actual_rows)
    archived_receipts = _fetch_archived_receipt_scope(conn, household_id=household_id)
    remaining_actual = actual_rows.copy()
    counts = Counter()
    failed_counts = Counter()
    details = []
    for expected in expected_rows:
        best_actual = None
        best_score = -1
        best_flags = {'filename_exact': False, 'store_match': False, 'total_match': False, 'line_count_match': False}
        best_match_reason = ''
        for actual in remaining_actual:
            score, flags, match_reason = _score_actual_match(expected, actual)
            if score > best_score:
                best_actual, best_score, best_flags, best_match_reason = actual, score, flags, match_reason
        if best_actual is None or best_score <= 0:
            counts['missing'] += 1
            counts['mapping_mismatch'] += 1
            details.append({'source_file': expected.get('source_file'), 'receipt_id': expected.get('receipt_id'), 'result': 'missing', 'po_norm_status': 'review_needed', 'po_norm_status_label': _status_label('review_needed'), 'difference_type': 'mapping_mismatch', 'failed_criteria': ['MISSING_ACTIVE_RECEIPT'], 'reason': 'Controle nodig: geen actieve receipt_table gevonden voor dit baselinebestand.', 'mapping_reason': best_match_reason, 'baseline_origin': expected.get('baseline_origin') or 'official_baseline_v4'})
            continue
        remaining_actual = [row for row in remaining_actual if row.get('receipt_table_id') != best_actual.get('receipt_table_id')]
        criteria = _po_criteria(expected, best_actual)
        for code in criteria['failed_criteria']:
            failed_counts[code] += 1
        result = 'correct' if criteria['all_criteria_pass'] else 'different'
        counts[result] += 1
        difference_type = None if result == 'correct' else (criteria['failed_criteria'][0].lower() if criteria['failed_criteria'] else 'po_norm_mismatch')
        if difference_type:
            counts[difference_type] += 1
        backend_status = str(best_actual.get('parse_status') or '').strip()
        details.append({'source_file': expected.get('source_file'), 'receipt_id': expected.get('receipt_id'), 'receipt_table_id': best_actual.get('receipt_table_id'), 'matched_original_filename': best_actual.get('original_filename'), 'expected_parse_status': 'approved', 'expected_status_label': _status_label('approved'), 'actual_parse_status': backend_status, 'actual_status_label': _status_label(backend_status), 'po_norm_status': criteria['po_norm_status'], 'po_norm_status_label': criteria['po_norm_status_label'], 'status_matches_po_norm': backend_status == criteria['po_norm_status'], 'expected_store_name': expected.get('store_name'), 'store_name': best_actual.get('store_name'), 'expected_total_amount': expected.get('total_amount'), 'total_amount': best_actual.get('total_amount'), 'expected_line_count': expected.get('line_count'), 'line_count': best_actual.get('line_count'), 'sum_line_total_used_for_decision': best_actual.get('sum_line_total_used_for_decision'), 'discount_total_used_for_decision': best_actual.get('discount_total_used_for_decision'), 'net_line_sum_used_for_decision': best_actual.get('net_line_sum_used_for_decision'), 'criteria': criteria, 'store_name_matches_baseline': criteria['store_name_matches_baseline'], 'total_amount_matches_baseline': criteria['total_amount_matches_baseline'], 'article_count_matches_baseline': criteria['article_count_matches_baseline'], 'line_sum_matches_total': criteria['line_sum_matches_total'], 'failed_criteria': criteria['failed_criteria'], 'result': result, 'difference_type': difference_type, 'reason': _reason(criteria), 'difference_reason': _reason(criteria), 'match_score': best_score, 'match_signals': best_flags, 'mapping_reason': None if best_flags.get('filename_exact') else best_match_reason, 'baseline_origin': expected.get('baseline_origin') or 'official_baseline_v4'})
    for actual in remaining_actual:
        counts['extra'] += 1
        counts['mapping_mismatch'] += 1
        details.append({'source_file': actual.get('original_filename'), 'receipt_table_id': actual.get('receipt_table_id'), 'actual_parse_status': actual.get('parse_status'), 'actual_status_label': _status_label(actual.get('parse_status')), 'po_norm_status': 'review_needed', 'po_norm_status_label': _status_label('review_needed'), 'result': 'extra', 'difference_type': 'mapping_mismatch', 'failed_criteria': ['NO_BASELINE_MATCH'], 'reason': 'Controle nodig: actieve receipt bestaat wel in database maar niet in de baseline.'})
    status_counts = Counter(item.get('po_norm_status_label') for item in details if item.get('po_norm_status_label'))
    backend_status_counts = Counter(item.get('actual_status_label') for item in details if item.get('actual_status_label'))
    summary = {'baseline_total': len(expected_rows), 'active_receipts_total': len(actual_rows), 'archived_receipts_total': len(archived_receipts), 'correct': counts['correct'], 'different': counts['different'], 'missing': counts['missing'], 'extra': counts['extra'], 'mapping_mismatch': counts['mapping_mismatch'], 'po_norm_status_counts': dict(status_counts), 'current_backend_status_counts': dict(backend_status_counts), 'failed_criteria_counts': dict(sorted(failed_counts.items()))}
    return {'runtime_datastore': get_runtime_datastore_info(), 'policy_source': 'receipt_status_baseline_service_v4.py', 'policy_mode': 'po_four_criteria_only', 'expected_status_file': str(EXPECTED_STATUS_PATH.name), 'criteria_file': str(CRITERIA_DOC_PATH.name), 'household_id': str(household_id) if household_id is not None else None, 'po_norm': {'status_gecontroleerd_when_all_true': ['winkelnaam gelijk aan baseline', 'totaalbedrag gelijk aan baseline', 'aantal artikelen gelijk aan baseline', 'som van artikelregels gelijk aan kassabontotaal'], 'article_description_affects_status': False, 'baseline_status_is_not_used_as_override': True, 'dev_fallback_baseline_used': False}, 'summary': summary, 'details': details, 'excluded_archived_receipts': archived_receipts}


def diagnose_receipt_status_baseline(conn, household_id: str | None = None) -> dict[str, Any]:
    validation = validate_receipt_status_baseline(conn, household_id=household_id)
    criterion_mismatches = []
    mapping_mismatches = []
    backend_status_mismatches = []
    for item in validation.get('details', []):
        if item.get('difference_type') == 'mapping_mismatch':
            mapping_mismatches.append(item)
        elif item.get('result') == 'different':
            criterion_mismatches.append(item)
        if item.get('actual_parse_status') and item.get('po_norm_status') and item.get('actual_parse_status') != item.get('po_norm_status'):
            backend_status_mismatches.append(item)
    return {'runtime_datastore': get_runtime_datastore_info(), 'policy_source': 'receipt_status_baseline_service_v4.py', 'policy_mode': 'po_four_criteria_only', 'validation_summary': validation.get('summary', {}), 'mapping_mismatch_count': len(mapping_mismatches), 'criterion_mismatch_count': len(criterion_mismatches), 'backend_status_mismatch_count': len(backend_status_mismatches), 'mapping_mismatches': mapping_mismatches, 'criterion_mismatches': criterion_mismatches, 'backend_status_mismatches': backend_status_mismatches, 'excluded_archived_receipts': validation.get('excluded_archived_receipts', [])}
