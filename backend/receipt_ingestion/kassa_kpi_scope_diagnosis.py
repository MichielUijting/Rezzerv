from __future__ import annotations

from typing import Any, Dict, List

try:
    from app.services.receipt_status_baseline_service import diagnose_receipt_status_baseline
except ModuleNotFoundError:  # repo-root import compatibility
    from backend.app.services.receipt_status_baseline_service import diagnose_receipt_status_baseline


def build_kassa_kpi_scope_diagnosis(conn, household_id: str | None = None) -> Dict[str, Any]:
    """Explain why the Kassa KPI scope is empty or incomplete.

    Read-only. Does not restore archived receipts, does not change receipt
    status, and does not write to the database.
    """
    diagnosis = diagnose_receipt_status_baseline(conn, household_id=household_id)
    active_scope = diagnosis.get('included_receipt_scope') or []
    archived_scope = diagnosis.get('excluded_archived_receipts') or []
    non_supermarket = diagnosis.get('excluded_non_supermarket_receipts') or []

    archived_receipts = [_summarize_receipt(row) for row in archived_scope]
    benchmark_candidates = [_summarize_receipt(row) for row in active_scope]

    candidate_from_archive = _derive_archive_benchmark_candidates(archived_receipts)

    if not active_scope and archived_scope:
        next_action = (
            'Alle gevonden kassabonnen vallen buiten de actieve KPI-scope omdat ze gearchiveerd/verwijderd zijn. '
            'Maak eerst een expliciete OCR-benchmarkset of herstel geselecteerde testbonnen bewust als actieve testdata.'
        )
    elif active_scope:
        next_action = 'Er zijn actieve kassabonnen beschikbaar; gebruik /api/receipt-kpi/baseline voor de KPI-meting.'
    else:
        next_action = 'Er zijn geen actieve of gearchiveerde kassabonnen gevonden in de huidige datastore.'

    return {
        'active_receipts_total': len(active_scope),
        'archived_receipts_total': len(archived_scope),
        'excluded_non_supermarket_total': len(non_supermarket),
        'benchmark_candidates': benchmark_candidates,
        'archived_benchmark_candidates': candidate_from_archive,
        'excluded_archived_receipts': archived_receipts,
        'recommended_next_action': next_action,
        'diagnostic_only': True,
        'no_db_write': True,
        'ssot_source': 'receipt_status_baseline_service',
    }


def _summarize_receipt(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'receipt_table_id': row.get('receipt_table_id'),
        'source_file': row.get('source_file') or row.get('original_filename') or row.get('matched_original_filename'),
        'store_name': row.get('store_name'),
        'purchase_at': row.get('purchase_at'),
        'total_amount': row.get('total_amount') or row.get('actual_total_amount'),
        'parse_status': row.get('parse_status') or row.get('actual_parse_status'),
        'line_count': row.get('line_count') or row.get('actual_line_count'),
        'deleted_at': row.get('deleted_at'),
    }


def _derive_archive_benchmark_candidates(archived_receipts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Suggest possible benchmark candidates without unarchiving anything."""
    seen = set()
    candidates = []
    for row in archived_receipts:
        source = str(row.get('source_file') or '').strip()
        if not source:
            continue
        key = ''.join(ch.lower() for ch in source if ch.isalnum())
        if key in seen:
            continue
        seen.add(key)
        candidates.append({
            'source_file': source,
            'store_name': row.get('store_name'),
            'total_amount': row.get('total_amount'),
            'parse_status': row.get('parse_status'),
            'candidate_reason': 'gearchiveerde bon met herkenbare bron; alleen kandidaat voor expliciete PO-benchmarkkeuze',
        })
    return candidates
