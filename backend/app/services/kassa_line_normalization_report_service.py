from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.receipt_ingestion.spaarzegels_terms import spaarzegels_financial_metadata

PACKAGE_RE = re.compile(
    r'(?<![a-z0-9])(\d+(?:[\.,]\d+)?)\s*(kg|g|gr|gram|ml|cl|l|liter)\b',
    re.IGNORECASE,
)
AMOUNT_RE = re.compile(r'(?<!\d)-?\d{1,6}[\.,]\d{2}(?!\d)')
TRAILING_OCR_FRAGMENT_RE = re.compile(r'(?:\s+[\u00c3\u00c2\u00e2\ufffd\u20ac]+)+\s*$')
MIXED_ALPHA_NUMERIC_TOKEN_RE = re.compile(r'\b(?=[A-Za-zÀ-ÖØ-öø-ÿ0-9]*[A-Za-zÀ-ÖØ-öø-ÿ])(?=[A-Za-zÀ-ÖØ-öø-ÿ0-9]*\d)[A-Za-zÀ-ÖØ-öø-ÿ0-9]{2,}\b')
ALPHA_ZERO_ALPHA_TOKEN_RE = re.compile(r'\b[A-Za-zÀ-ÖØ-öø-ÿ]+0[A-Za-zÀ-ÖØ-öø-ÿ0-9]*\b')
SUSPICIOUS_EDGE_TOKEN_RE = re.compile(r'(^|\s)[^A-Za-zÀ-ÖØ-öø-ÿ0-9\s]{1,2}(\s|$)|(^|\s)[A-Za-zÀ-ÖØ-öø-ÿ0-9]?[^A-Za-zÀ-ÖØ-öø-ÿ0-9\s][A-Za-zÀ-ÖØ-öø-ÿ0-9]?(\s|$)')
ALPHA_TOKEN_RE = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]+')
NUMERIC_SUFFIX_WITHOUT_UNIT_RE = re.compile(r'\b\d{2,5}\s*$')
MOJIBAKE_CODEPOINTS = {0x00C3, 0x00C2, 0x00E2, 0xFFFD}
MOJIBAKE_TWO_CHAR_SEQUENCES = (
    '\u00c3\u0080', '\u00c3\u0081', '\u00c3\u0082', '\u00c3\u0083', '\u00c3\u0084', '\u00c3\u0085',
    '\u00c3\u0087', '\u00c3\u0088', '\u00c3\u0089', '\u00c3\u008a', '\u00c3\u008b',
    '\u00c3\u00a0', '\u00c3\u00a1', '\u00c3\u00a2', '\u00c3\u00a3', '\u00c3\u00a4', '\u00c3\u00a5',
    '\u00c3\u00a7', '\u00c3\u00a8', '\u00c3\u00a9', '\u00c3\u00aa', '\u00c3\u00ab',
    '\u00c2\u00ae', '\u00c2\u00a9', '\u00c2\u00b0', '\u00c2\u00b1', '\u00c2\u00b7',
    '\u00e2\u201a', '\u00e2\u20ac',
)
TRUNCATED_ALL_CAPS_FINAL_CHARS = set('BDFGHJKLMPRV')
TRUNCATED_LOWER_FINAL_BIGRAMS = {'df', 'gm', 'kr', 'nm', 'vk'}
COMMON_ALL_CAPS_FINAL_SUFFIXES = (
    'AAS', 'ANK', 'AUS', 'BOL', 'DEN', 'ERS', 'EEN', 'ELS', 'GEN', 'GEL', 'ING', 'JES',
    'KER', 'MELK', 'MIX', 'OEK', 'OEN', 'PEN', 'PES', 'PIZZA', 'PREI', 'RIJST', 'SAUS',
    'SNOEP', 'TEN', 'TER', 'WATER', 'WIT',
)
PRODUCT_NAME_ENRICHMENT_RULES_PATH = Path(__file__).with_name('product_name_enrichment_rules.json')


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


def _contains_residual_encoding_artifact(text_value: str) -> bool:
    value = str(text_value or '')
    if not value:
        return False
    if any(sequence in value for sequence in MOJIBAKE_TWO_CHAR_SEQUENCES):
        return True
    return any(ord(char) in MOJIBAKE_CODEPOINTS for char in value)


def _alpha_tokens(text_value: str) -> list[str]:
    return ALPHA_TOKEN_RE.findall(text_value or '')


def _is_all_caps_alpha_token(token: str) -> bool:
    return token.isalpha() and token.upper() == token and token.lower() != token


def _is_short_abbreviation_token(token: str) -> bool:
    return _is_all_caps_alpha_token(token) and len(token) <= 3


def _has_possible_truncated_word(text_value: str, alpha_tokens: list[str]) -> bool:
    if not alpha_tokens:
        return False
    token = alpha_tokens[-1].strip()
    if len(token) < 5:
        return False
    if _is_all_caps_alpha_token(token):
        if token.endswith(COMMON_ALL_CAPS_FINAL_SUFFIXES):
            return False
        if re.search(r'[BCDFGHJKLMNPQRSTVWXZ]{3,}$', token):
            return True
        return 5 <= len(token) <= 8 and token[-1] in TRUNCATED_ALL_CAPS_FINAL_CHARS
    lower = token.lower()
    if lower[-2:] in TRUNCATED_LOWER_FINAL_BIGRAMS:
        return True
    return bool(re.search(r'[bcdfghjklmnpqrstvwxz]{3,}$', lower))


def _normalize_enrichment_key(value: str | None) -> str:
    normalized = _s(value).upper()
    normalized = re.sub(r'[^A-ZÀ-ÖØ-Þ0-9]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


@lru_cache(maxsize=1)
def _product_name_enrichment_rules() -> dict[str, dict[str, Any]]:
    if not PRODUCT_NAME_ENRICHMENT_RULES_PATH.exists():
        return {}
    try:
        raw_rules = json.loads(PRODUCT_NAME_ENRICHMENT_RULES_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    rules: dict[str, dict[str, Any]] = {}
    for raw_rule in raw_rules if isinstance(raw_rules, list) else []:
        if not isinstance(raw_rule, dict):
            continue
        if raw_rule.get('match_type') != 'exact_normalized_label':
            continue
        label_key = _normalize_enrichment_key(raw_rule.get('label'))
        suggested_product_name = _s(raw_rule.get('suggested_product_name'))
        if not label_key or not suggested_product_name:
            continue
        rules[label_key] = {
            'suggested_product_name': suggested_product_name,
            'match_type': 'exact_normalized_label',
            'matched_label': raw_rule.get('label'),
            'source': raw_rule.get('source') or 'product_name_enrichment_rules',
            'confidence': raw_rule.get('confidence') or 'medium',
        }
    return rules


def _product_name_enrichment_suggestion(label: str | None) -> dict[str, Any] | None:
    key = _normalize_enrichment_key(label)
    if not key:
        return None
    rule = _product_name_enrichment_rules().get(key)
    if not rule:
        return None
    return {
        'suggested_product_name': rule['suggested_product_name'],
        'product_name_enrichment_applied': True,
        'product_name_enrichment_match_type': rule['match_type'],
        'product_name_enrichment_source': rule['source'],
        'product_name_enrichment_confidence': rule['confidence'],
        'product_name_enrichment_matched_label': rule['matched_label'],
    }


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
    if _contains_residual_encoding_artifact(combined):
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

    alpha_tokens = _alpha_tokens(visible_label)
    short_alpha_tokens = [token for token in alpha_tokens if _is_short_abbreviation_token(token)]
    all_caps_tokens = [token for token in alpha_tokens if _is_all_caps_alpha_token(token)]
    if short_alpha_tokens:
        findings.append('product_name_short_abbreviation_token_detected')
    if len(short_alpha_tokens) >= 2:
        findings.append('product_name_multiple_short_tokens_detected')
    if short_alpha_tokens and len(all_caps_tokens) >= 2:
        findings.append('product_name_all_caps_abbreviation_pattern_detected')
    if _has_possible_truncated_word(visible_label, alpha_tokens):
        findings.append('product_name_possible_truncated_word_detected')
    if NUMERIC_SUFFIX_WITHOUT_UNIT_RE.search(visible_label) and not PACKAGE_RE.search(visible_label):
        findings.append('product_name_numeric_suffix_without_unit_detected')

    if article_name and _s(article_name) != visible_label:
        findings.append('product_name_candidate_differs_from_stored_label')
    return findings


def _normalization_findings(
    row: dict[str, Any],
    role: str,
    package: dict[str, Any] | None,
    article_name: str | None,
    product_name_noise: list[str] | None = None,
    product_name_enrichment: dict[str, Any] | None = None,
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
        if product_name_enrichment:
            findings.append('product_name_enrichment_suggestion_available')
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
    product_name_enrichment = _product_name_enrichment_suggestion(normalized_label or raw_label) if role == 'product_line' else None
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
        'product_name_enrichment': product_name_enrichment,
        **(package or {
            'package_quantity_detected': None,
            'package_unit_detected': None,
            'package_text_detected': None,
        }),
        'line_type': financial_metadata.get('line_type') if financial_metadata else None,
        'is_spaarzegels': bool(financial_metadata.get('is_spaarzegels')) if financial_metadata else False,
        'exclude_from_inventory': bool(financial_metadata.get('exclude_from_inventory')) if financial_metadata else not include_in_inventory_flow,
        'matched_spaarzegels_term': financial_metadata.get('matched_spaarzegels_term') if financial_metadata else None,
        'normalization_findings': _normalization_findings(row, role, package, article_name, product_name_noise, product_name_enrichment),
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
    product_name_enrichment_suggestions = [
        line.get('product_name_enrichment')
        for line in lines
        if line.get('product_name_enrichment')
    ]
    product_name_enrichment_counts = Counter(
        str(suggestion.get('confidence') or 'unknown')
        for suggestion in product_name_enrichment_suggestions
        if isinstance(suggestion, dict)
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
            'product_name_enrichment_suggestion_count': len(product_name_enrichment_suggestions),
            'product_name_enrichment_confidence_counts': dict(product_name_enrichment_counts),
        },
        'guardrails': {
            'mutates_inventory': False,
            'creates_inventory_event': False,
            'creates_product_group_assignment': False,
            'creates_catalog_link': False,
            'changes_receipt_status': False,
            'uses_parse_status_as_category_source': False,
            'overwrites_receipt_labels': False,
        },
        'lines': lines,
    }
