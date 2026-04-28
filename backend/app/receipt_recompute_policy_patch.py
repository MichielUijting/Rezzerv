from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text

from app.domains.receipts.receipt_status_policy import decide_receipt_status

POLICY_SOURCE = 'receipt_status_policy.py'


def _line_sum_matches_total(total_amount: Any, line_total_sum: Any) -> bool | None:
    try:
        return abs(float(total_amount) - float(line_total_sum)) < 0.01
    except Exception:
        return None


def build_policy_recompute_report(conn, household_id: Optional[str] = None, limit: Optional[int] = None) -> dict[str, Any]:
    query = """
        SELECT
            rt.id,
            rt.household_id,
            rt.store_name,
            rt.total_amount,
            rt.parse_status,
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
    """
    params: dict[str, Any] = {}
    conditions = []
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
            line_count = int(row.get('line_count') or 0)
            line_total_sum = row.get('line_total_sum')
            line_sum_matches_total = _line_sum_matches_total(row.get('total_amount'), line_total_sum)
            decision = decide_receipt_status(
                store_name_matches_baseline=None,
                total_amount_matches_baseline=None,
                article_count_matches_baseline=None,
                line_sum_matches_total=line_sum_matches_total,
            )
            next_parse_status = str(decision.parse_status or 'review_needed').strip().lower() or 'review_needed'
            inbox_status = str(decision.inbox_status or 'Controle nodig')

            report['status_counts'][inbox_status] = int(report['status_counts'].get(inbox_status, 0) or 0) + 1
            report['parse_status_counts'][next_parse_status] = int(report['parse_status_counts'].get(next_parse_status, 0) or 0) + 1

            current_parse_status = str(row.get('parse_status') or '').strip().lower()
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
                'store_name': row.get('store_name'),
                'line_count': line_count,
                'total_amount': row.get('total_amount'),
                'line_total_sum': line_total_sum,
                'line_sum_matches_total': line_sum_matches_total,
                'status': inbox_status,
                'parse_status': next_parse_status,
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
