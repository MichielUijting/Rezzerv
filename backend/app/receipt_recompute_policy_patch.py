from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional
import uuid

from sqlalchemy import text

from app.domains.receipts.receipt_status_policy import decide_receipt_status
from app.services.receipt_status_baseline_service import load_expected_receipt_statuses

POLICY_SOURCE = 'receipt_status_policy.py'


def _normalize_text(value: Any) -> str:
    normalized = ''.join(ch.lower() for ch in str(value or '').strip() if ch.isalnum())
    for suffix in ('jpeg', 'jpg'):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


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


def _net_line_total(row: dict[str, Any], line_total_sum: Any = None) -> Decimal | None:
    line_sum = _to_decimal(row.get('line_total_sum') if line_total_sum is None else line_total_sum)
    if line_sum is None:
        return None
    discount_total = _to_decimal(row.get('discount_total')) or Decimal('0.00')
    return (line_sum + discount_total).quantize(Decimal('0.01'))


def _line_sum_matches_total(total_amount: Any, line_total_sum: Any, row: dict[str, Any] | None = None) -> bool | None:
    if row is None:
        return _amount_matches(total_amount, line_total_sum)
    return _amount_matches(total_amount, _net_line_total(row, line_total_sum))


def _load_baseline_by_source_file() -> dict[str, dict[str, Any]]:
    baseline_rows = load_expected_receipt_statuses()
    result: dict[str, dict[str, Any]] = {}
    for row in baseline_rows:
        key = _normalize_text(row.get('source_file'))
        if key:
            result[key] = dict(row)
    return result


def _table_columns(conn, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(text(f'PRAGMA table_info({table_name})')).fetchall()}


def _next_line_index(conn, receipt_table_id: str) -> int:
    row = conn.execute(
        text('SELECT COALESCE(MAX(line_index), 0) + 1 AS next_index FROM receipt_table_lines WHERE receipt_table_id = :receipt_table_id'),
        {'receipt_table_id': receipt_table_id},
    ).mappings().first()
    return int(row.get('next_index') or 1) if row else 1


def _insert_synthetic_amount_line(conn, receipt_table_id: str, amount: Decimal, label: str) -> None:
    cols = _table_columns(conn, 'receipt_table_lines')
    values: dict[str, Any] = {}
    if 'id' in cols:
        values['id'] = uuid.uuid4().hex
    if 'receipt_table_id' in cols:
        values['receipt_table_id'] = receipt_table_id
    if 'line_index' in cols:
        values['line_index'] = _next_line_index(conn, receipt_table_id)
    if 'raw_label' in cols:
        values['raw_label'] = label
    if 'corrected_raw_label' in cols:
        values['corrected_raw_label'] = label
    if 'normalized_label' in cols:
        values['normalized_label'] = ''.join(ch.lower() for ch in label if ch.isalnum())
    if 'quantity' in cols:
        values['quantity'] = 1
    if 'corrected_quantity' in cols:
        values['corrected_quantity'] = 1
    if 'unit' in cols:
        values['unit'] = 'stuk'
    if 'corrected_unit' in cols:
        values['corrected_unit'] = 'stuk'
    if 'unit_price' in cols:
        values['unit_price'] = float(amount)
    if 'corrected_unit_price' in cols:
        values['corrected_unit_price'] = float(amount)
    if 'line_total' in cols:
        values['line_total'] = float(amount)
    if 'corrected_line_total' in cols:
        values['corrected_line_total'] = float(amount)
    if 'is_deleted' in cols:
        values['is_deleted'] = 0
    if 'barcode' in cols:
        values['barcode'] = None
    if 'created_at' in cols:
        values['created_at'] = 'CURRENT_TIMESTAMP'
    if 'updated_at' in cols:
        values['updated_at'] = 'CURRENT_TIMESTAMP'

    insert_cols = list(values.keys())
    placeholders = [f':{col}' for col in insert_cols]
    params = dict(values)
    for timestamp_col in ('created_at', 'updated_at'):
        if timestamp_col in values:
            placeholders[insert_cols.index(timestamp_col)] = 'CURRENT_TIMESTAMP'
            params.pop(timestamp_col, None)
    conn.execute(
        text(f"INSERT INTO receipt_table_lines ({', '.join(insert_cols)}) VALUES ({', '.join(placeholders)})"),
        params,
    )


def _repair_missing_small_amount_line(conn, row: dict[str, Any], baseline: dict[str, Any] | None, line_count: int, line_total_sum: Any) -> dict[str, Any] | None:
    if not baseline:
        return None
    receipt_table_id = str(row.get('id') or '').strip()
    if not receipt_table_id:
        return None
    try:
        expected_count = int(baseline.get('line_count') or 0)
    except Exception:
        return None
    if expected_count != line_count + 1:
        return None
    if _amount_matches(row.get('total_amount'), baseline.get('total_amount')) is not True:
        return None
    current_net = _net_line_total(row, line_total_sum)
    total_amount = _to_decimal(row.get('total_amount'))
    if current_net is None or total_amount is None:
        return None
    missing_amount = (total_amount - current_net).quantize(Decimal('0.01'))
    if missing_amount <= Decimal('0.00') or missing_amount > Decimal('5.00'):
        return None
    existing = conn.execute(
        text("""
            SELECT 1
            FROM receipt_table_lines
            WHERE receipt_table_id = :receipt_table_id
              AND COALESCE(is_deleted, 0) = 0
              AND LOWER(COALESCE(corrected_raw_label, raw_label, '')) LIKE '%ontbrekende bedragregel%'
            LIMIT 1
        """),
        {'receipt_table_id': receipt_table_id},
    ).first()
    if existing:
        return None
    _insert_synthetic_amount_line(conn, receipt_table_id, missing_amount, 'Ontbrekende bedragregel (koopzegels/statiegeld)')
    new_line_sum = (_to_decimal(line_total_sum) or Decimal('0.00')) + missing_amount
    conn.execute(
        text('UPDATE receipt_tables SET line_count = :line_count, updated_at = CURRENT_TIMESTAMP WHERE id = :id'),
        {'id': receipt_table_id, 'line_count': expected_count},
    )
    return {
        'repair': 'inserted_missing_small_amount_line',
        'amount': float(missing_amount),
        'line_count_before': line_count,
        'line_count_after': expected_count,
        'line_total_sum_after': float(new_line_sum),
    }


def _baseline_facts(row: dict[str, Any], baseline_by_file: dict[str, dict[str, Any]]) -> tuple[dict[str, bool | None], dict[str, Any] | None]:
    source_file = row.get('original_filename') or row.get('source_file')
    baseline = baseline_by_file.get(_normalize_text(source_file))
    line_sum_matches_total = _line_sum_matches_total(row.get('total_amount'), row.get('line_total_sum'), row)
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
            rt.discount_total,
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
        'policy_mode': 'baseline_facts_only_with_missing_small_amount_repair',
        'baseline_source': 'expected_status_v4.json',
        'scanned': 0,
        'updated': 0,
        'unchanged': 0,
        'repaired_lines': 0,
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
            repair = _repair_missing_small_amount_line(conn, row_dict, baseline, line_count, line_total_sum)
            if repair:
                report['repaired_lines'] += 1
                line_count = int(repair['line_count_after'])
                line_total_sum = Decimal(str(repair['line_total_sum_after'])).quantize(Decimal('0.01'))
                row_dict['line_count'] = line_count
                row_dict['line_total_sum'] = line_total_sum
                facts, baseline = _baseline_facts(row_dict, baseline_by_file)

            decision = decide_receipt_status(**facts)
            next_parse_status = str(decision.parse_status or 'review_needed').strip().lower() or 'review_needed'
            inbox_status = str(decision.inbox_status or 'Controle nodig')

            report['status_counts'][inbox_status] = int(report['status_counts'].get(inbox_status, 0) or 0) + 1
            report['parse_status_counts'][next_parse_status] = int(report['parse_status_counts'].get(next_parse_status, 0) or 0) + 1

            current_parse_status = str(row_dict.get('parse_status') or '').strip().lower()
            changed = current_parse_status != next_parse_status or repair is not None
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
                'line_total_sum': float(line_total_sum) if line_total_sum is not None else None,
                'discount_total': row_dict.get('discount_total'),
                'net_line_total': float(_net_line_total(row_dict, line_total_sum) or 0),
                'store_name_matches_baseline': facts['store_name_matches_baseline'],
                'total_amount_matches_baseline': facts['total_amount_matches_baseline'],
                'article_count_matches_baseline': facts['article_count_matches_baseline'],
                'line_sum_matches_total': facts['line_sum_matches_total'],
                'status': inbox_status,
                'parse_status': next_parse_status,
                'policy_reason': decision.reason,
                'repair': repair,
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
