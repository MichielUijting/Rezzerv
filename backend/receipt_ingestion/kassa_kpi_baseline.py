from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

try:
    from app.services.receipt_status_baseline_service import diagnose_receipt_status_baseline
except ModuleNotFoundError:  # repo-root import compatibility
    from backend.app.services.receipt_status_baseline_service import diagnose_receipt_status_baseline

TARGET_STATUS_LABEL = 'Gecontroleerd'


def build_kassa_kpi_baseline(conn, household_id: str | None = None) -> Dict[str, Any]:
    """Build a PO-oriented KPI report using the existing SSOT status baseline.

    This runner does not determine receipt status. It reads the current outcome
    from the existing SSOT baseline service and only summarizes whether the
    current Kassa/receipt flow reaches the PO target: Gecontroleerd.
    """
    diagnosis = diagnose_receipt_status_baseline(conn, household_id=household_id)
    included_scope = diagnosis.get('included_receipt_scope') or []
    details_by_source = _index_diagnosis_details(diagnosis)

    items: List[Dict[str, Any]] = []
    for scope_item in included_scope:
        source_file = str(scope_item.get('source_file') or '').strip()
        detail = details_by_source.get(_normalize(source_file), {})
        current_label = _status_label(
            detail.get('actual_status_label')
            or scope_item.get('parse_status')
            or detail.get('actual_parse_status')
        )
        matches_target = current_label == TARGET_STATUS_LABEL
        failure_reason = None if matches_target else _failure_reason(scope_item, detail)
        recommended_area = None if matches_target else _recommended_improvement_area(detail, failure_reason)
        items.append(
            {
                'receipt_id': scope_item.get('receipt_table_id') or detail.get('receipt_id') or source_file,
                'source_file': source_file,
                'store_name': scope_item.get('store_name') or detail.get('store_name') or '-',
                'current_ssot_status': current_label,
                'target_status': TARGET_STATUS_LABEL,
                'matches_target': matches_target,
                'failure_reason': failure_reason,
                'recommended_improvement_area': recommended_area,
                'line_count': scope_item.get('line_count') or detail.get('line_count'),
                'total_amount': scope_item.get('total_amount') or detail.get('total_amount'),
            }
        )

    counts = Counter()
    area_counts = Counter()
    store_counts = Counter()
    for item in items:
        if item.get('matches_target'):
            counts['gecontroleerd'] += 1
        else:
            counts['nog_niet_gecontroleerd'] += 1
            area = item.get('recommended_improvement_area') or 'unknown'
            area_counts[area] += 1
            store_counts[str(item.get('store_name') or '-')] += 1

    first_priority = _first_priority(area_counts, store_counts)
    active_count = len(items)

    return {
        'target_status': TARGET_STATUS_LABEL,
        'active_receipts_total': active_count,
        'current_gecontroleerd': counts['gecontroleerd'],
        'current_not_gecontroleerd': counts['nog_niet_gecontroleerd'],
        'current_score_percent': round((counts['gecontroleerd'] / active_count) * 100, 1) if active_count else 0.0,
        'regressions': 0,
        'first_improvement_priority': first_priority,
        'improvement_area_breakdown': dict(sorted(area_counts.items())),
        'store_breakdown_not_gecontroleerd': dict(sorted(store_counts.items())),
        'items': items,
        'ssot_source': 'receipt_status_baseline_service',
        'diagnostic_only': True,
        'no_status_written': True,
        'excluded_archived_receipts_total': len(diagnosis.get('excluded_archived_receipts') or []),
        'excluded_non_supermarket_total': len(diagnosis.get('excluded_non_supermarket_receipts') or []),
    }


def _index_diagnosis_details(diagnosis: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for bucket_name in ('extraction_mismatches', 'mapping_mismatches', 'status_logic_mismatches', 'extra_receipts'):
        for item in diagnosis.get(bucket_name) or []:
            key = _normalize(item.get('source_file') or item.get('matched_original_filename'))
            if key:
                indexed[key] = item
    return indexed


def _status_label(value: Any) -> str:
    raw = str(value or '').strip()
    if raw == 'approved':
        return 'Gecontroleerd'
    if raw == 'review_needed':
        return 'Controle nodig'
    if raw == 'manual':
        return 'Handmatig'
    return raw or 'Onbekend'


def _failure_reason(scope_item: Dict[str, Any], detail: Dict[str, Any]) -> str:
    if detail.get('diagnosis'):
        return str(detail.get('diagnosis'))
    if detail.get('difference_reason'):
        return str(detail.get('difference_reason'))
    status = _status_label(scope_item.get('parse_status'))
    if status == 'Controle nodig':
        return 'SSOT geeft Controle nodig: regelsom, totaal of artikelregels zijn nog niet sluitend genoeg.'
    if status == 'Handmatig':
        return 'SSOT geeft Handmatig: winkelnaam, totaalprijs of geldige artikelregels ontbreken.'
    return 'Bon haalt de doelstatus Gecontroleerd nog niet.'


def _recommended_improvement_area(detail: Dict[str, Any], failure_reason: str | None) -> str:
    dtype = str(detail.get('difference_type') or '').strip()
    reason = str(failure_reason or '').lower()
    if dtype == 'mapping_mismatch' or 'geen passende actieve receipt' in reason or 'niet betrouwbaar gekoppeld' in reason:
        return 'kassa_mapping'
    if dtype == 'status_logic_mismatch':
        return 'ssot_validation'
    if 'totaalprijs ontbreekt' in reason or 'totaal' in reason:
        return 'parser_total'
    if 'geen geldige artikellijnen' in reason or 'artikel' in reason or 'regelsom' in reason:
        return 'parser_article_lines'
    if dtype == 'extraction_mismatch':
        return 'ocr_or_parser_extraction'
    return 'store_profile_or_preprocessing'


def _first_priority(area_counts: Counter, store_counts: Counter) -> str:
    if not area_counts:
        return 'Geen directe tuning nodig: alle actieve bonnen halen de doelstatus.'
    area, count = area_counts.most_common(1)[0]
    store_suffix = ''
    if store_counts:
        store, store_count = store_counts.most_common(1)[0]
        store_suffix = f' Meest geraakt: {store} ({store_count}).'
    return f'Eerste verbetergebied: {area} ({count} bonnen).{store_suffix}'


def _normalize(value: Any) -> str:
    return ''.join(ch.lower() for ch in str(value or '').strip() if ch.isalnum())
