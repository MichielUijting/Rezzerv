from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text

from app.domains.receipts.receipt_status_policy import decide_receipt_status
from app.services.receipt_status_baseline_service import load_expected_receipt_statuses

POLICY_SOURCE = 'receipt_status_policy.py'


def _normalize_text(value: Any) -> str:
    return ''.join(ch.lower() for ch in str(value or '').strip() if ch.isalnum())


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except Exception:
        return None


def _amount_matches(left: Any, right: Any, tolerance: Decimal = Decimal('0.01')) -> bool | None:
    left_dec = _to_decimal(left)
    right_dec = _to_decimal(right)
    if left_dec is None or right_dec is None:
        return None
    return abs(left_dec - right_dec) <= tolerance


def _line_sum_matches_total(total_amount: Any, line_total_sum: Any) -> bool | None:
    return _amount_matches(total_amount, line_total_sum)


def _load_baseline_by_source_file() -> dict[str, dict[str, Any]]:
    baseline_rows = load_expected_receipt_statuses()
    result: dict[str, dict[str, Any]] = {}
    for row in baseline_rows:
        key = _normalize_text(row.get('source_file'))
        if key:
            result[key] = dict(row)
    return result


def _baseline_facts(row: dict[str, Any], baseline_by_file: dict[str, dict[str, Any]]) -> tuple[dict[str, bool | None], dict[str, Any] | None]:
    source_file = row.get('original_filename') or row.get('source_file')
    baseline = baseline_by_file.get(_normalize_text(source_file))
    line_sum_matches_total = _line_sum_matches_total(row.get('total_amount'), row.get('line_total_sum'))
    if not baseline:
        return {
            'store_name_matches_baseline': None,
            'total_amount_matches_baseline': None,
            'article_count_matches_baseline': None,
            'line_sum_matches_total': line_sum_matches_total,
        }, None

    store_name_matches_baseline = _normalize_text(row.get('store_name')) == _normalize_text(baseline.get('store_name'))
    total_amount_matches_baseline = _amount_matches(row.get('total_amount'), baseline.get('total_amount'))
    try:
        article_count_matches_baseline = int(row.get('line_count') or 0) == int(baseline.get('line_count') or 0)
    except Exception:
        article_count_matches_baseline = None

    return {
        'store_name_matches_baseline': store_name_matches_baseline,
        'total_amount_matches_baseline': total_amount_matches_baseline,
        'article_count_matches_baseline': article_count_matches_baseline,
        'line_sum_matches_total': line_sum_matches_total,
    }, baseline


def build_policy_recompute_report(conn, household_id: Optional[str] = None, limit: Optional[int] = None) -> dict[str, Any]:
    baseline_by_file = _load_baseline_by_source_file()
    query = """
        SELECT
            rt.id,
            rt.household_id,
            rt.store_name,
            rt.total_amount,
            rt.parse_status,
            rr.original_filename,
            (
                SELECT COUNT(*)
                FROM receipt_table_lines rtl_count
                WHERE rtl_count.receipt_table_id = rt.id
                  AND COALESCE(rtl_count.is_deleted, 0) = 0
                  AND TRIM(COALESCE(rtl_count.corrected_raw_label, rtl_count.raw_label, '')) <> ''
            ) AS line_count,
            (
                SELECT COALESCE(SUM(COALESCE(rtl.corrected_line_total, rtl.line_total, 0)), 0)
                FROM receipt_table_lines rtl
                WHERE rtl.receipt_table_id = rt.id
                  AND COALESCE(rtl.is_deleted, 0) = 0
            ) AS line_total_sum
        FROM receipt_tables rt
        JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
    """
    params: dict[str, Any] = {}
    conditions = ['rt.deleted_at IS NULL']
    if household_id is not None:
        conditions.append('rt.household_id = :household_id')
        params['household_id'] = str(household_id)
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY rt.created_at DESC'
    if limit is not None:
        query += ' LIMIT :limit'
        params['limit'] = int(limit)

    rows = conn.execute(text(query), params).mappings().all()
    report: dict[str, Any] = {
        'policy_source': POLICY_SOURCE,
        'policy_mode': 'baseline_facts_only',
        'baseline_source': 'expected_status_v3.json',
        'scanned': 0,
        'updated': 0,
        'unchanged': 0,
        'errors': 0,
        'status_counts': {'Gecontroleerd': 0, 'Controle nodig': 0, 'Handmatig': 0},
        'parse_status_counts': {},
        'lines': {},
    }

    for row in rows:
        receipt_id = str(row.get('id') or '').strip()
        if not receipt_id:
            continue
        report['scanned'] += 1
        try:
            row_dict = dict(row)
            line_count = int(row_dict.get('line_count') or 0)
            line_total_sum = row_dict.get('line_total_sum')
            facts, baseline = _baseline_facts(row_dict, baseline_by_file)
            decision = decide_receipt_status(**facts)
            next_parse_status = str(decision.parse_status or 'review_needed').strip().lower() or 'review_needed'
            inbox_status = str(decision.inbox_status or 'Controle nodig')

            report['status_counts'][inbox_status] = int(report['status_counts'].get(inbox_status, 0) or 0) + 1
            report['parse_status_counts'][next_parse_status] = int(report['parse_status_counts'].get(next_parse_status, 0) or 0) + 1

            current_parse_status = str(row_dict.get('parse_status') or '').strip().lower()
            changed = current_parse_status != next_parse_status
            if changed:
                conn.execute(
                    text("""
                        UPDATE receipt_tables
                        SET parse_status = :parse_status,
                            line_count = :line_count,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    """),
                    {'id': receipt_id, 'parse_status': next_parse_status, 'line_count': line_count},
                )
                report['updated'] += 1
            else:
                report['unchanged'] += 1

            report['lines'][receipt_id] = {
                'policy_source': POLICY_SOURCE,
                'source_file': row_dict.get('original_filename'),
                'baseline_source_file': baseline.get('source_file') if baseline else None,
                'store_name': row_dict.get('store_name'),
                'expected_store_name': baseline.get('store_name') if baseline else None,
                'line_count': line_count,
                'expected_line_count': baseline.get('line_count') if baseline else None,
                'total_amount': row_dict.get('total_amount'),
                'expected_total_amount': baseline.get('total_amount') if baseline else None,
                'line_total_sum': line_total_sum,
                'store_name_matches_baseline': facts['store_name_matches_baseline'],
                'total_amount_matches_baseline': facts['total_amount_matches_baseline'],
                'article_count_matches_baseline': facts['article_count_matches_baseline'],
                'line_sum_matches_total': facts['line_sum_matches_total'],
                'status': inbox_status,
                'parse_status': next_parse_status,
                'policy_reason': decision.reason,
            }
        except Exception as exc:
            report['errors'] += 1
            report['lines'][receipt_id] = {'policy_source': POLICY_SOURCE, 'error': str(exc)}
    return report


def install_recompute_policy_patch(main_module) -> bool:
    if getattr(main_module, '_rezzerv_recompute_policy_patch_installed', False):
        return False

    def backfill_receipt_unpack_statuses(conn, household_id: Optional[str] = None, limit: Optional[int] = None):
        return build_policy_recompute_report(conn, household_id=household_id, limit=limit)

    main_module.backfill_receipt_unpack_statuses = backfill_receipt_unpack_statuses
    main_module._rezzerv_recompute_policy_patch_installed = True
    return True
