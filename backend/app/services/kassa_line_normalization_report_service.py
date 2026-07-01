from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.receipt_ingestion.spaarzegels_terms import spaarzegels_financial_metadata

PACKAGE_RE = re.compile(
    r'(?<![a-z0-9])(\d+(?:[\.,]\d+)?)\s*(kg|g|gr|gram|ml|cl|l|liter)\b',
    re.IGNORECASE,
)
AMOUNT_RE = re.compile(r'(?<!\d)-?\d{1,6}[\.,]\d{2}(?!\d)')
MOJIBAKE_MARKER_RE = re.compile(r'(?:Ã|Â|â[\u0080-\u00bf\u2018-\u201d\u20ac]|�)')
TRAILING_OCR_FRAGMENT_RE = re.compile(r'(?:\s+[ÃÂâ�€]+)+\s*$')
MIXED_ALPHA_NUMERIC_TOKEN_RE = re.compile(r'\b(?=[A-Za-zÀ-ÖØ-öø-ÿ0-9]*[A-Za-zÀ-ÖØ-öø-ÿ])(?=[A-Za-zÀ-ÖØ-öø-ÿ0-9]*\d)[A-Za-zÀ-ÖØ-öø-ÿ0-9]{2,}\b')
ALPHA_ZERO_ALPHA_TOKEN_RE = re.compile(r'\b[A-Za-zÀ-ÖØ-öø-ÿ]+0[A-Za-zÀ-ÖØ-öø-ÿ0-9]*\b')
SUSPICIOUS_EDGE_TOKEN_RE = re.compile(r'(^|\s)[^A-Za-zÀ-ÖØ-öø-ÿ0-9\s]{1,2}(\s|$)|(^|\s)[A-Za-zÀ-ÖØ-öø-ÿ0-9]?[^A-Za-zÀ-ÖØ-öø-ÿ0-9\s][A-Za-zÀ-ÖØ-öø-ÿ0-9]?(\s|$)')


def _s(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


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


def _line_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _s(row.get(key))
        if value:
            return value
    return ''


def _stored_quantity(row: dict[str, Any]) -> Any:
    return row.get('quantity')


def _stored_unit(row: dict[str, Any]) -> str:
    return _s(row.get('unit'))


def _stored_price(row: dict[str, Any]) -> Any:
    return row.get('line_total')


def _detect_package(text_value: str) -> dict[str, Any] | None:
    match = PACKAGE_RE.search(text_value or '')
    if not match:
        return None
    quantity_text = match.group(1).replace(',', '.')
    try:
        quantity: Any = float(quantity_text)
        if float(quantity).is_integer():
            quantity = int(quantity)
    except ValueError:
        quantity = quantity_text
    unit = match.group(2).lower()
    if unit == 'gr':
        unit = 'g'
    if unit == 'gram':
        unit = 'g'
    if unit == 'liter':
        unit = 'l'
    return {
        'package_quantity_detected': quantity,
        'package_unit_detected': unit,
        'package_text_detected': match.group(0),
    }


def _generic_article_name_candidate(text_value: str) -> str | None:
    candidate = _s(text_value)
    if not candidate:
        return None
    candidate = AMOUNT_RE.sub(' ', candidate)
    candidate = PACKAGE_RE.sub(' ', candidate)
    candidate = re.sub(r'(?<![a-z])\b\d+\s*[x×]\s*', ' ', candidate, flags=re.IGNORECASE)
    candidate = re.sub(r'\s+', ' ', candidate).strip(' .:-')
    if not re.search(r'[A-Za-zÀ-ÖØ-öø-ÿ]', candidate):
        return None
    return candidate or None


def _spaarzegels_metadata(row: dict[str, Any]) -> dict[str, Any]:
    raw_label = _line_text(row, 'raw_label', 'normalized_label')
    normalized_label = _line_text(row, 'normalized_label', 'raw_label')
    return spaarzegels_financial_metadata(
        raw_label,
        label_text=normalized_label,
        detail_text=f'{raw_label} {normalized_label} {_stored_price(row) or ""}',
    )


def _line_role(row: dict[str, Any], financial_metadata: dict[str, Any]) -> str:
    if financial_metadata:
        return 'financial_loyalty_line'
    if _stored_price(row) not in {None, ''} and _generic_article_name_candidate(_line_text(row, 'normalized_label', 'raw_label')):
        return 'product_line'
    if _stored_price(row) not in {None, ''}:
        return 'financial_or_unknown_line'
    return 'unclassified_line'


def _product_name_noise_findings(raw_label: str, normalized_label: str, article_name: str | None) -> list[str]:
    findings: list[str] = []
    combined = _s(f'{raw_label} {normalized_label} {article_name or ""}')
    visible_label = _s(normalized_label or raw_label)
    if not combined:
        return findings
    if MOJIBAKE_MARKER_RE.search(combined):
        findings.append('product_name_residual_encoding_artifact_detected')
    if TRAILING_OCR_FRAGMENT_RE.search(raw_label) or TRAILING_OCR_FRAGMENT_RE.search(normalized_label):
        findings.append('product_name_trailing_ocr_fragment_detected')
    mixed_tokens = MIXED_ALPHA_NUMERIC_TOKEN_RE.findall(visible_label)
    if mixed_tokens:
        findings.append('product_name_mixed_alphanumeric_token_detected')
    if ALPHA_ZERO_ALPHA_TOKEN_RE.search(visible_label):
        findings.append('product_name_zero_inside_alpha_token_detected')
    if SUSPICIOUS_EDGE_TOKEN_RE.search(visible_label):
        findings.append('product_name_suspicious_symbol_token_detected')
    if article_name and _s(article_name) != visible_label:
        findings.append('product_name_candidate_differs_from_stored_label')
    return findings


def _normalization_findings(
    row: dict[str, Any],
    role: str,
    package: dict[str, Any] | None,
    article_name: str | None,
    product_name_noise: list[str] | None = None,
) -> list[str]:
    findings: list[str] = []
    stored_quantity = _stored_quantity(row)
    stored_unit = _stored_unit(row)
    if role == 'product_line' and package and (stored_quantity in {None, ''} or not stored_unit):
        findings.append('package_detected_in_label_but_not_stored_separately')
    if role == 'product_line' and not article_name:
        findings.append('missing_article_name_candidate')
    if role == 'product_line' and _stored_price(row) in {None, ''}:
        findings.append('missing_line_price')
    if role == 'product_line':
        findings.extend(product_name_noise or [])
    if role == 'financial_loyalty_line':
        findings.append('financial_line_excluded_from_inventory_and_external_matching')
    return findings


def _diagnosis_line(receipt: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    raw_label = _line_text(row, 'raw_label', 'normalized_label')
    normalized_label = _line_text(row, 'normalized_label', 'raw_label')
    text_for_detection = f'{raw_label} {normalized_label}'.strip()
    financial_metadata = _spaarzegels_metadata(row)
    role = _line_role(row, financial_metadata)
    package = _detect_package(text_for_detection)
    article_name = None if role == 'financial_loyalty_line' else _generic_article_name_candidate(normalized_label or raw_label)
    product_name_noise = _product_name_noise_findings(raw_label, normalized_label, article_name) if role == 'product_line' else []
    include_in_inventory_flow = role == 'product_line'
    external_matching_allowed = role == 'product_line'
    return {
        'receipt_table_id': str(receipt.get('receipt_table_id') or ''),
        'store_name': receipt.get('store_name'),
        'purchase_at': str(receipt.get('purchase_at')) if receipt.get('purchase_at') is not None else None,
        'line_id': str(row.get('id') or ''),
        'line_index': int(row.get('line_index') or 0),
        'raw_line': raw_label,
        'stored_raw_label': raw_label,
        'stored_normalized_label': normalized_label,
        'stored_quantity': _num(_stored_quantity(row)),
        'stored_unit': _stored_unit(row) or None,
        'stored_line_price': _num(_stored_price(row)),
        'detected_line_role': role,
        'include_in_receipt_total': _stored_price(row) not in {None, ''},
        'include_in_inventory_flow': include_in_inventory_flow,
        'external_matching_allowed': external_matching_allowed,
        'article_name_candidate': article_name,
        'article_name_candidate_normalized': article_name.lower() if article_name else None,
        'product_name_noise_findings': product_name_noise,
        **(package or {
            'package_quantity_detected': None,
            'package_unit_detected': None,
            'package_text_detected': None,
        }),
        'line_type': financial_metadata.get('line_type') if financial_metadata else None,
        'is_spaarzegels': bool(financial_metadata.get('is_spaarzegels')) if financial_metadata else False,
        'exclude_from_inventory': bool(financial_metadata.get('exclude_from_inventory')) if financial_metadata else not include_in_inventory_flow,
        'matched_spaarzegels_term': financial_metadata.get('matched_spaarzegels_term') if financial_metadata else None,
        'normalization_findings': _normalization_findings(row, role, package, article_name, product_name_noise),
    }


def build_kassa_line_normalization_report(
    engine,
    household_id: str | None = None,
    limit: int = 100,
    include_inactive: bool = False,
) -> dict[str, Any]:
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
    role_counts = Counter(str(line.get('detected_line_role') or 'unknown') for line in lines)
    finding_counts = Counter(
        finding
        for line in lines
        for finding in (line.get('normalization_findings') or [])
    )
    product_name_noise_counts = Counter(
        finding
        for line in lines
        for finding in (line.get('product_name_noise_findings') or [])
    )
    return {
        'ok': True,
        'diagnosis_type': 'kassa_line_normalization_report',
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
            'role_counts': dict(role_counts),
            'normalization_finding_counts': dict(finding_counts),
            'product_name_noise_finding_counts': dict(product_name_noise_counts),
        },
        'guardrails': {
            'mutates_inventory': False,
            'creates_inventory_event': False,
            'creates_product_group_assignment': False,
            'creates_catalog_link': False,
            'changes_receipt_status': False,
            'uses_parse_status_as_category_source': False,
        },
        'lines': lines,
    }
