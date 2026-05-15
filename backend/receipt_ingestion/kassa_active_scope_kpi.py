from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from sqlalchemy import text

TARGET_STATUS_LABEL = 'Gecontroleerd'

STATUS_LABELS = {
    'approved': 'Gecontroleerd',
    'approved_override': 'Gecontroleerd',
    'review_needed': 'Controle nodig',
    'manual': 'Handmatig',
    'failed': 'Niet herkend',
    'parsed': 'Geparsed',
    'partial': 'Gedeeltelijk herkend',
}


def build_active_kassa_scope_kpi(conn, household_id: str | None = None) -> dict[str, Any]:
    rows = _fetch_active_receipts(conn, household_id=household_id)
    archived_count = _count_archived_receipts(conn, household_id=household_id)

    items = []
    area_counts = Counter()
    store_counts = Counter()
    gecontroleerd = 0

    for row in rows:
        label = _status_label(row.get('parse_status'))
        matches = label == TARGET_STATUS_LABEL
        if matches:
            gecontroleerd += 1
            failure_reason = None
            area = None
        else:
            failure_reason = _failure_reason(row, label)
            area = _recommended_area(row, failure_reason)
            area_counts[area] += 1
            store_counts[str(row.get('store_name') or '-')] += 1
        items.append({
            'receipt_id': row.get('receipt_table_id'),
            'source_file': row.get('original_filename'),
            'store_name': row.get('store_name') or '-',
            'current_ssot_status': label,
            'raw_parse_status': row.get('parse_status'),
            'target_status': TARGET_STATUS_LABEL,
            'matches_target': matches,
            'failure_reason': failure_reason,
            'recommended_improvement_area': area,
            'line_count': row.get('line_count'),
            'active_line_count': row.get('active_line_count'),
            'total_amount': row.get('total_amount'),
            'line_sum': row.get('active_line_sum'),
            'line_sum_matches_total': _amount_equals(row.get('total_amount'), row.get('active_line_sum')),
        })

    total = len(items)
    return {
        'target_status': TARGET_STATUS_LABEL,
        'active_receipts_total': total,
        'current_gecontroleerd': gecontroleerd,
        'current_not_gecontroleerd': total - gecontroleerd,
        'current_score_percent': round((gecontroleerd / total) * 100, 1) if total else 0.0,
        'regressions': 0,
        'first_improvement_priority': _first_priority(area_counts, store_counts),
        'improvement_area_breakdown': dict(sorted(area_counts.items())),
        'store_breakdown_not_gecontroleerd': dict(sorted(store_counts.items())),
        'items': items,
        'scope_source': 'kassa_active_receipts',
        'ssot_status_field': 'receipt_tables.parse_status',
        'diagnostic_only': True,
        'no_status_written': True,
        'excluded_archived_receipts_total': archived_count,
    }


def _fetch_active_receipts(conn, household_id: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    sql = """
        SELECT
            rt.id AS receipt_table_id,
            rr.original_filename,
            rt.store_name,
            rt.total_amount,
            rt.discount_total,
            rt.line_count,
            rt.parse_status,
            rt.created_at,
            COALESCE(SUM(CASE WHEN COALESCE(rtl.is_deleted, 0) = 0 THEN COALESCE(rtl.corrected_line_total, rtl.line_total, 0) ELSE 0 END), 0) AS active_line_sum,
            SUM(CASE WHEN COALESCE(rtl.is_deleted, 0) = 0 THEN 1 ELSE 0 END) AS active_line_count
        FROM receipt_tables rt
        JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
        LEFT JOIN receipt_table_lines rtl ON rtl.receipt_table_id = rt.id
        WHERE rt.deleted_at IS NULL
    """
    if household_id is not None:
        sql += " AND rt.household_id = :household_id"
        params['household_id'] = str(household_id)
    sql += """
        GROUP BY rt.id, rr.original_filename, rt.store_name, rt.total_amount,
                 rt.discount_total, rt.line_count, rt.parse_status, rt.created_at
        ORDER BY rt.created_at DESC, rt.id DESC
    """
    return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]


def _count_archived_receipts(conn, household_id: str | None = None) -> int:
    params: dict[str, Any] = {}
    sql = 'SELECT COUNT(*) AS n FROM receipt_tables WHERE deleted_at IS NOT NULL'
    if household_id is not None:
        sql += ' AND household_id = :household_id'
        params['household_id'] = str(household_id)
    row = conn.execute(text(sql), params).mappings().first()
    return int(row.get('n') or 0) if row else 0


def _status_label(value: Any) -> str:
    raw = str(value or '').strip()
    return STATUS_LABELS.get(raw, raw or 'Onbekend')


def _failure_reason(row: dict[str, Any], current_label: str) -> str:
    store = str(row.get('store_name') or '').strip()
    if not store or store.lower() in {'onbekend', 'unknown', 'onbekende winkel'}:
        return 'Winkelnaam ontbreekt of is niet betrouwbaar herkend.'
    if row.get('total_amount') in (None, ''):
        return 'Totaalbedrag ontbreekt of is niet betrouwbaar herkend.'
    if int(row.get('active_line_count') or 0) < 1:
        return 'Er zijn geen actieve artikelregels herkend.'
    if current_label == 'Controle nodig':
        return 'Bon staat op Controle nodig: regels, totaal of artikelregels sluiten nog niet betrouwbaar genoeg aan.'
    return f'Bon haalt Gecontroleerd nog niet; huidige status is {current_label}.'


def _recommended_area(row: dict[str, Any], reason: str | None) -> str:
    text = str(reason or '').lower()
    if 'winkelnaam' in text:
        return 'store_profile'
    if 'totaal' in text:
        return 'parser_total'
    if 'artikelregels' in text or 'regels' in text:
        return 'parser_article_lines'
    if str(row.get('parse_status') or '') in {'failed', 'manual'}:
        return 'ocr_or_preprocessing'
    return 'parser_or_profile_tuning'


def _first_priority(area_counts: Counter, store_counts: Counter) -> str:
    if not area_counts:
        return 'Geen directe tuning nodig: alle actieve bonnen halen de doelstatus.'
    area, count = area_counts.most_common(1)[0]
    suffix = ''
    if store_counts:
        store, store_count = store_counts.most_common(1)[0]
        suffix = f' Meest geraakt: {store} ({store_count}).'
    return f'Eerste verbetergebied: {area} ({count} bonnen).{suffix}'


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ''):
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
