from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.receipt_ingestion.spaarzegels_terms import spaarzegels_financial_metadata

PACKAGE_UNITS = {'g', 'gr', 'gram', 'kg', 'ml', 'cl', 'l', 'liter'}
NOISE_TERMS = {'totaal', 'subtotaal', 'pin', 'contant', 'btw', 'wisselgeld', 'betaald', 'bonus', 'korting', 'kassa', 'filiaal'}
SUSPICIOUS_PATTERN = re.compile(r'(\b[0-9][a-z]{2,}\b|\b[a-z]+[0-9][a-z0-9]*\b|\?)', re.IGNORECASE)


def _num(value: Any) -> Any:
    if value is None or value == '':
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number.is_integer() else number


def _s(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _line_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _s(row.get(key))
        if value:
            return value
    return ''


def _qty(row: dict[str, Any]) -> Any:
    return row.get('quantity')


def _unit(row: dict[str, Any]) -> str:
    return _s(row.get('unit'))


def _price(row: dict[str, Any]) -> Any:
    return row.get('line_total')


def _article(row: dict[str, Any]) -> str:
    return _line_text(row, 'normalized_label', 'raw_label')


def _off_query(row: dict[str, Any]) -> str:
    article = _article(row).lower()
    unit = _unit(row).lower()
    quantity = _qty(row)
    if article and quantity not in {None, ''} and unit in PACKAGE_UNITS:
        return f"{article} {str(_num(quantity)).replace('.', ',')} {unit}".strip()
    return article


def _spaarzegels_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return spaarzegels_financial_metadata(
        _line_text(row, 'raw_label', 'normalized_label'),
        label_text=_line_text(row, 'normalized_label', 'raw_label'),
        detail_text=_line_text(row, 'raw_label', 'normalized_label'),
    )


def _diagnosis_line(receipt: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    quantity = _qty(row)
    unit = _unit(row)
    financial_metadata = _spaarzegels_metadata(row)
    line = {
        'receipt_table_id': str(receipt.get('receipt_table_id') or ''),
        'store_name': receipt.get('store_name'),
        'purchase_at': str(receipt.get('purchase_at')) if receipt.get('purchase_at') is not None else None,
        'line_id': str(row.get('id') or ''),
        'line_index': int(row.get('line_index') or 0),
        'raw_line': _line_text(row, 'raw_label', 'normalized_label'),
        'clean_line': _line_text(row, 'normalized_label', 'raw_label'),
        'article_name': _article(row),
        'quantity_value': _num(quantity),
        'quantity_unit': unit or None,
        'package_size_label': f"{str(_num(quantity)).replace('.', ',')} {unit}".strip() if quantity not in {None, ''} else None,
        'line_price': _num(_price(row)),
        'unit_price': _num(row.get('unit_price')),
        'discount_amount': _num(row.get('discount_amount')),
        'barcode': _s(row.get('barcode')) or None,
        'off_query': _off_query(row),
        'parser_status': 'diagnose_available' if _article(row) and _price(row) not in {None, ''} else 'needs_review',
        'parser_confidence': _num(row.get('confidence_score')),
    }
    if financial_metadata:
        line.update({
            'line_type': financial_metadata.get('line_type'),
            'is_spaarzegels': bool(financial_metadata.get('is_spaarzegels')),
            'include_in_receipt_total': bool(financial_metadata.get('include_in_receipt_total')),
            'exclude_from_inventory': bool(financial_metadata.get('exclude_from_inventory')),
            'external_matching_allowed': bool(financial_metadata.get('external_matching_allowed')),
            'matched_spaarzegels_term': financial_metadata.get('matched_spaarzegels_term'),
            'diagnosis_note': 'financial_non_inventory_line',
        })
    return line


def _is_spaarzegels_financial_line(line: dict[str, Any]) -> bool:
    return (
        line.get('line_type') == 'spaarzegels'
        or line.get('is_spaarzegels') is True
        or (
            line.get('exclude_from_inventory') is True
            and line.get('external_matching_allowed') is False
        )
    )


def _is_noise(line: dict[str, Any]) -> bool:
    if _is_spaarzegels_financial_line(line):
        return False
    text_value = f"{line.get('raw_line') or ''} {line.get('clean_line') or ''} {line.get('article_name') or ''}".lower()
    if any(term in text_value for term in NOISE_TERMS):
        return True
    compact = re.sub(r'[^0-9,.-]', '', text_value)
    return bool(compact and re.fullmatch(r'-?\d+[,.]\d{2}', compact))


def _finding(severity: str, finding_type: str, line: dict[str, Any], recommendation: str) -> dict[str, Any]:
    return {
        'severity': severity,
        'type': finding_type,
        'receipt_table_id': line.get('receipt_table_id'),
        'store_name': line.get('store_name'),
        'line_index': line.get('line_index'),
        'example': line.get('raw_line') or line.get('article_name') or line.get('off_query'),
        'off_query': line.get('off_query'),
        'recommendation': recommendation,
    }


def _findings(lines: list[dict[str, Any]], max_findings: int) -> tuple[dict[str, int], list[dict[str, Any]]]:
    summary = Counter()
    findings: list[dict[str, Any]] = []
    for line in lines:
        raw = str(line.get('raw_line') or '')
        query = str(line.get('off_query') or '').strip()
        is_spaarzegels = _is_spaarzegels_financial_line(line)
        if is_spaarzegels:
            summary['spaarzegels_financial_lines'] += 1
            continue
        if line.get('line_price') in {None, ''}:
            summary['lines_without_price'] += 1
            findings.append(_finding('high', 'missing_price', line, 'Controleer prijsdetectie: deze regel heeft geen herkende regelprijs.'))
        if line.get('quantity_value') in {None, ''}:
            summary['lines_without_quantity'] += 1
        if line.get('quantity_value') in {None, ''} and re.search(r'\b\d+(?:[,.]\d+)?\s?(kg|g|gr|ml|cl|l)\b', raw, re.IGNORECASE):
            summary['missed_package_size'] += 1
            findings.append(_finding('high', 'missed_package_size', line, 'Herken verpakkingseenheden zoals 1 L, 400 g, 250 ml of 1 kg.'))
        if SUSPICIOUS_PATTERN.search(raw + ' ' + query):
            summary['suspicious_ocr_terms'] += 1
            findings.append(_finding('medium', 'suspicious_ocr_terms', line, 'Voeg tekstnormalisatie toe voor verdachte cijfer-lettercombinaties.'))
        if len(query) < 4 or (len(query.split()) == 1 and len(query) <= 4):
            summary['short_or_noisy_off_queries'] += 1
            findings.append(_finding('medium', 'short_or_noisy_off_query', line, 'Verbeter de OFF-zoektekst door bonafkortingen te normaliseren.'))
        if _is_noise(line):
            summary['potential_non_article_lines'] += 1
            findings.append(_finding('high', 'potential_non_article_line', line, 'Filter totaal-, betaal-, korting- en BTW-regels eerder uit.'))
    order = {'high': 0, 'medium': 1, 'low': 2}
    findings.sort(key=lambda item: (order.get(str(item.get('severity')), 9), str(item.get('type'))))
    return dict(summary), findings[:max(1, max_findings)]


def build_kassa_parse_quality_report(engine, household_id: str | None = None, limit: int = 100, include_inactive: bool = False, max_findings: int = 50) -> dict[str, Any]:
    normalized_household_id = str(household_id or '').strip()
    where = [] if include_inactive else ["COALESCE(rt.deleted_at, '') = ''", "COALESCE(rr.deleted_at, '') = ''"]
    params: dict[str, Any] = {'limit': max(1, min(int(limit or 100), 500))}
    if normalized_household_id:
        where.append('rt.household_id = :household_id')
        params['household_id'] = normalized_household_id
    where_sql = ' AND '.join(where) if where else '1 = 1'
    with engine.begin() as conn:
        receipts = conn.execute(text(f"""
            SELECT rt.id AS receipt_table_id, rt.raw_receipt_id, rt.household_id, rt.store_name,
                   rt.purchase_at, rt.total_amount, rt.parse_status, rt.line_count, rt.created_at,
                   rr.original_filename
            FROM receipt_tables rt
            JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
            WHERE {where_sql}
            ORDER BY datetime(rt.created_at) DESC, rt.id DESC
            LIMIT :limit
        """), params).mappings().all()
        lines: list[dict[str, Any]] = []
        for receipt_row in receipts:
            receipt = dict(receipt_row)
            line_rows = conn.execute(text("""
                SELECT id, line_index, raw_label, normalized_label, quantity, unit, unit_price,
                       line_total, discount_amount, barcode, confidence_score
                FROM receipt_table_lines
                WHERE receipt_table_id = :receipt_table_id
                ORDER BY line_index ASC, id ASC
            """), {'receipt_table_id': str(receipt['receipt_table_id'])}).mappings().all()
            for row in line_rows:
                lines.append(_diagnosis_line(receipt, dict(row)))
    summary, top_findings = _findings(lines, max_findings=max_findings)
    stores = Counter(str(row.get('store_name') or 'onbekend') for row in receipts)
    statuses = Counter(str(row.get('parse_status') or 'onbekend') for row in receipts)
    return {
        'ok': True,
        'diagnosis_type': 'kassa_parse_quality_report',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'selection': {
            'household_id_filter': normalized_household_id or None,
            'limit': params['limit'],
            'include_inactive': bool(include_inactive),
            'scope': 'active_receipts_only' if not include_inactive else 'active_and_archived_receipts',
        },
        'summary': {
            'receipt_count': len(receipts),
            'line_count': len(lines),
            'spaarzegels_financial_lines': summary.get('spaarzegels_financial_lines', 0),
            'lines_without_price': summary.get('lines_without_price', 0),
            'lines_without_quantity': summary.get('lines_without_quantity', 0),
            'missed_package_size': summary.get('missed_package_size', 0),
            'suspicious_ocr_terms': summary.get('suspicious_ocr_terms', 0),
            'short_or_noisy_off_queries': summary.get('short_or_noisy_off_queries', 0),
            'potential_non_article_lines': summary.get('potential_non_article_lines', 0),
        },
        'stores': dict(stores),
        'parse_statuses': dict(statuses),
        'top_findings': top_findings,
        'recommendations': [
            {'priority': 1, 'release_hint': 'M2C2i-32C', 'topic': 'Productnaam-normalisatie'},
            {'priority': 2, 'release_hint': 'M2C2i-32D', 'topic': 'Hoeveelheid en verpakking herkennen'},
        ],
        'mutates_inventory': False,
        'creates_inventory_event': False,
        'creates_product_group_assignment': False,
        'creates_catalog_link': False,
    }
