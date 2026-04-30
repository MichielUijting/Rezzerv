from __future__ import annotations

from typing import Any, Optional

from app.services.receipt_status_baseline_service import validate_receipt_status_baseline

POLICY_SOURCE = 'receipt_status_baseline_service_v4.py'
POLICY_MODE = 'single_canonical_po_four_criteria_with_supermarket_reconciliation'


def _build_line_payload(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        'policy_source': POLICY_SOURCE,
        'policy_mode': POLICY_MODE,
        'source_file': detail.get('matched_original_filename') or detail.get('source_file'),
        'baseline_source_file': detail.get('source_file'),
        'store_name': detail.get('store_name'),
        'expected_store_name': detail.get('expected_store_name'),
        'line_count': detail.get('line_count'),
        'expected_line_count': detail.get('expected_line_count'),
        'total_amount': detail.get('total_amount'),
        'expected_total_amount': detail.get('expected_total_amount'),
        'line_total_sum': detail.get('sum_line_total_used_for_decision'),
        'discount_total': detail.get('discount_total_used_for_decision'),
        'net_line_total': detail.get('net_line_sum_used_for_decision'),
        'store_name_matches_baseline': detail.get('store_name_matches_baseline'),
        'total_amount_matches_baseline': detail.get('total_amount_matches_baseline'),
        'article_count_matches_baseline': detail.get('article_count_matches_baseline'),
        'line_sum_matches_total': detail.get('line_sum_matches_total'),
        'status': detail.get('po_norm_status_label') or detail.get('actual_status_label'),
        'parse_status': detail.get('po_norm_status') or detail.get('actual_parse_status'),
        'policy_reason': detail.get('reason') or detail.get('difference_reason'),
        'failed_criteria': detail.get('failed_criteria') or [],
        'baseline_reconciliation_applied': bool(detail.get('baseline_reconciliation_applied')),
        'repair': None,
    }


def build_policy_recompute_report(conn, household_id: Optional[str] = None, limit: Optional[int] = None) -> dict[str, Any]:
    """Single canonical receipt recompute route."""
    validation = validate_receipt_status_baseline(conn, household_id=household_id)
    details = validation.get('details', [])
    if limit is not None:
        details = details[: int(limit)]

    status_counts = {'Gecontroleerd': 0, 'Controle nodig': 0, 'Handmatig': 0}
    parse_status_counts: dict[str, int] = {}
    lines: dict[str, dict[str, Any]] = {}
    errors = 0

    for detail in details:
        receipt_id = str(detail.get('receipt_table_id') or detail.get('receipt_id') or detail.get('source_file') or '')
        if not receipt_id:
            continue
        try:
            line_payload = _build_line_payload(detail)
            status_label = str(line_payload.get('status') or 'Controle nodig')
            parse_status = str(line_payload.get('parse_status') or 'review_needed')
            status_counts[status_label] = int(status_counts.get(status_label, 0) or 0) + 1
            parse_status_counts[parse_status] = int(parse_status_counts.get(parse_status, 0) or 0) + 1
            lines[receipt_id] = line_payload
        except Exception as exc:
            errors += 1
            lines[receipt_id] = {'policy_source': POLICY_SOURCE, 'policy_mode': POLICY_MODE, 'error': str(exc)}

    summary = validation.get('summary', {})
    scanned = int(summary.get('active_receipts_total') or len(lines))
    updated = int(summary.get('status_updated_to_po_norm') or 0)
    return {
        'policy_source': POLICY_SOURCE,
        'policy_mode': POLICY_MODE,
        'baseline_source': validation.get('expected_status_file') or 'expected_status_v4.json',
        'scanned': scanned,
        'updated': updated,
        'unchanged': max(scanned - updated, 0),
        'repaired_lines': 0,
        'baseline_reconciliation_applied': int(summary.get('baseline_reconciliation_applied') or 0),
        'errors': errors,
        'status_counts': status_counts,
        'parse_status_counts': parse_status_counts,
        'validation_summary': summary,
        'lines': lines,
    }


def install_recompute_policy_patch(main_module) -> bool:
    if getattr(main_module, '_rezzerv_recompute_policy_patch_installed', False):
        return False

    def backfill_receipt_unpack_statuses(conn, household_id: Optional[str] = None, limit: Optional[int] = None):
        return build_policy_recompute_report(conn, household_id=household_id, limit=limit)

    main_module.backfill_receipt_unpack_statuses = backfill_receipt_unpack_statuses
    main_module._rezzerv_recompute_policy_patch_installed = True
    return True
