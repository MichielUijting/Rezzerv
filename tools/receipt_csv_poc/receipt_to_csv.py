from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import pytesseract
from PIL import Image

from line_classifier import classify_lines, summarize_line_types
from profiles import get_profile_for_store
from profiles.base import PARSEABLE_LINE_TYPES

AMOUNT_PATTERN = re.compile(r'(?<!\d)(-?\d+[\.,]\d{2})(?!\d)')
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}
DISCOUNT_KEYWORDS = ('korting', 'voordeel', 'lidl plus', 'bonus')
TOTAL_KEYWORDS = ('totaal', 'te betalen', 'kaartbetaling')
TOTAL_HINT_EXCLUDE_KEYWORDS = ('prijsvoordeel', 'totaal korting', 'btw totaal', 'biw totaal')
SUMMARY_DISCOUNT_KEYWORDS = ('totaal prijsvoordeel', 'totaal korting')
RESCUE_STOP_LINE_TYPES = {'total_line', 'payment_line', 'vat_line'}
RESCUE_EXCLUDED_LINE_TYPES = {'metadata_line', 'payment_line', 'vat_line', 'discount_line', 'noise_line', 'total_line'}
CURRENCY_WORDS_PATTERN = re.compile(r'\b(eur|euro)\b', re.IGNORECASE)
CURRENCY_SYMBOLS_PATTERN = re.compile(r'[€$£]')
GENERIC_LOYALTY_KEYWORDS = ('zegel', 'zegels', 'campagne', 'spaar', 'spaarkaart', 'loyalty')
STORE_LOYALTY_KEYWORDS = {
    'plus': ('pluspunten', 'pluspunt', 'digitale zegels'),
    'lidl': ('lidl plus',),
    'ah': ('bonus box', 'bonuskaart'),
    'jumbo': ('extra\'s', 'jumbo extra'),
}
NAME_AMOUNT_LINK_MAX_DISTANCE = 4
NAME_AMOUNT_LINK_HEADER_KEYWORDS = (
    'omschrijving', 'omschrtjving', 'prijs', 'bedrag', 'aantal', 'subtotaal',
    'totaal', 'betaald', 'waarvan', 'terminal', 'merchant', 'transactie',
    'klantticket', 'periode', 'token', 'kaart', 'tel:',
)
NAME_AMOUNT_LINK_STORE_HEADER_KEYWORDS = {
    'ah': ('albert heijn',),
    'plus': ('plus',),
    'jumbo': ('jumbo supermarkt',),
    'lidl': ('lidl nederland',),
    'aldi': ('aldi',),
}


@dataclass
class ReceiptLine:
    source_file: str
    store_hint: str
    profile_name: str
    line_no: int
    line_type: str
    item_text: str
    quantity: str
    unit: str
    unit_price: str
    line_total: str
    parser_confidence: float
    raw_line: str
    warning: str


@dataclass
class ReceiptResult:
    source_file: str
    run_result: str
    store_hint: str
    profile_name: str
    detected_rows: int
    ignored_line_count: int
    line_type_counts: dict
    merge_diagnostics: dict
    refinement_diagnostics: dict
    totals_diagnostics: dict
    product_block_rescue_diagnostics: dict
    product_name_amount_link_diagnostics: dict
    amount_only_exclusion_diagnostics: dict
    loyalty_exclusion_diagnostics: dict


def normalize_decimal(value: str) -> str:
    return value.replace(',', '.').strip()


def to_decimal(value: str | int | float | Decimal | None) -> Decimal:
    if value is None or value == '':
        return Decimal('0')
    try:
        return Decimal(str(value).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal('0.01')))


def detect_store_hint(text: str, filename: str) -> str:
    combined = f'{filename}\n{text}'.lower()
    if 'lidl' in combined:
        return 'lidl'
    if 'jumbo' in combined:
        return 'jumbo'
    if 'aldi' in combined:
        return 'aldi'
    if 'plus' in combined:
        return 'plus'
    if 'albert heijn' in combined or re.search(r'\bah\b', combined):
        return 'ah'
    return 'unknown'


def parse_quantity(line: str):
    quantity = ''
    unit = ''
    unit_price = ''

    match = re.search(r'(\d+[\.,]?\d*)\s*[xX]\s*(\d+[\.,]\d{2})', line)
    if match:
        quantity = normalize_decimal(match.group(1))
        unit = 'stuk'
        unit_price = normalize_decimal(match.group(2))

    weight_match = re.search(r'(\d+[\.,]\d+)\s*(kg|g|l|ml)\s*[xX]\s*(\d+[\.,]\d{2})', line, re.IGNORECASE)
    if weight_match:
        quantity = normalize_decimal(weight_match.group(1))
        unit = weight_match.group(2)
        unit_price = normalize_decimal(weight_match.group(3))

    return quantity, unit, unit_price


def parse_receipt_lines(text: str, source_file: str, store_hint: str, profile_name: str, classified_lines, product_block):
    rows = []

    for classified in classified_lines:
        if classified.line_type not in PARSEABLE_LINE_TYPES:
            continue

        if product_block.get('start_line') and classified.line_no < product_block['start_line']:
            continue

        if product_block.get('end_line') and classified.line_no > product_block['end_line']:
            continue

        line = classified.normalized_line
        amounts = AMOUNT_PATTERN.findall(line)
        if not amounts:
            continue

        last_amount = normalize_decimal(amounts[-1])
        item_text = line.replace(amounts[-1], '').strip()
        quantity, unit, unit_price = parse_quantity(line)

        rows.append(
            ReceiptLine(
                source_file=source_file,
                store_hint=store_hint,
                profile_name=profile_name,
                line_no=classified.line_no,
                line_type=classified.line_type,
                item_text=item_text,
                quantity=quantity,
                unit=unit,
                unit_price=unit_price,
                line_total=last_amount,
                parser_confidence=0.75,
                raw_line=classified.raw_line,
                warning='quantity_line_requires_merge' if classified.line_type == 'quantity_line' else '',
            )
        )

    return rows


def extract_amounts(line: str) -> list[Decimal]:
    return [to_decimal(amount) for amount in AMOUNT_PATTERN.findall(line)]


def _candidate(line, amount: Decimal, reason: str) -> dict:
    return {
        'line_no': line.line_no,
        'amount': money(amount),
        'raw_line': line.raw_line,
        'reason': reason,
    }


def select_total_hint(total_candidates: list[dict]) -> tuple[dict | None, list[dict]]:
    selected = None
    excluded = []
    for candidate in total_candidates:
        lowered = str(candidate.get('raw_line', '')).lower()
        if any(keyword in lowered for keyword in TOTAL_HINT_EXCLUDE_KEYWORDS):
            excluded.append({**candidate, 'excluded_reason': 'summary_or_tax_total_not_payable_total'})
            continue
        if selected is None:
            selected = {**candidate, 'selected_total_hint_reason': 'first_payable_total_like_line'}
        else:
            previous_amount = to_decimal(selected.get('amount'))
            current_amount = to_decimal(candidate.get('amount'))
            if current_amount == previous_amount:
                selected = {**candidate, 'selected_total_hint_reason': 'later_matching_payable_total_like_line'}
            else:
                excluded.append({**candidate, 'excluded_reason': 'conflicting_total_hint_after_selection'})
    return selected, excluded


def select_discount_total(discount_candidates: list[dict]) -> tuple[Decimal, str, list[dict], list[dict]]:
    summary_candidates = []
    individual_candidates = []
    for candidate in discount_candidates:
        lowered = str(candidate.get('raw_line', '')).lower()
        if any(keyword in lowered for keyword in SUMMARY_DISCOUNT_KEYWORDS):
            summary_candidates.append(candidate)
        else:
            individual_candidates.append(candidate)

    if summary_candidates:
        selected = summary_candidates[-1]
        excluded = [{**candidate, 'excluded_reason': 'summary_discount_total_selected'} for candidate in individual_candidates]
        return to_decimal(selected.get('amount')), 'summary_discount_total', [selected], excluded

    selected_candidates = individual_candidates
    selected_total = sum((to_decimal(item['amount']) for item in selected_candidates), Decimal('0'))
    return selected_total, 'sum_individual_discount_lines', selected_candidates, []


def build_delta_diagnostics(rows: list[ReceiptLine], classified_lines: list, difference: Decimal) -> dict:
    abs_difference = difference.copy_abs()
    suspicious_amounts = []
    amount_delta_candidates = []
    possible_duplicate_lines = []
    seen: dict[tuple[str, str], dict] = {}

    for row in rows:
        amount = to_decimal(row.line_total)
        entry = {
            'line_no': row.line_no,
            'amount': money(amount),
            'item_text': row.item_text,
            'raw_line': row.raw_line,
            'reason': 'parsed_output_line',
        }
        if amount == abs_difference:
            suspicious_amounts.append({**entry, 'suspicion_reason': 'amount_equals_abs_net_vs_selected_total_difference'})
        key = (row.item_text.lower().strip(), money(amount))
        if key in seen:
            possible_duplicate_lines.append({
                'first_line_no': seen[key]['line_no'],
                'duplicate_line_no': row.line_no,
                'amount': money(amount),
                'item_text': row.item_text,
                'reason': 'same_item_text_and_amount',
            })
        else:
            seen[key] = entry

    for line in classified_lines:
        amounts = extract_amounts(line.normalized_line or '')
        for amount in amounts:
            if amount == abs_difference:
                amount_delta_candidates.append({
                    'line_no': line.line_no,
                    'amount': money(amount),
                    'raw_line': line.raw_line,
                    'line_type': line.line_type,
                    'reason': 'ocr_line_amount_equals_abs_net_vs_selected_total_difference',
                })

    possible_missing_discount_application = []
    if abs_difference != Decimal('0'):
        for candidate in amount_delta_candidates:
            lowered = str(candidate.get('raw_line', '')).lower()
            if any(keyword in lowered for keyword in DISCOUNT_KEYWORDS):
                possible_missing_discount_application.append({**candidate, 'reason': 'discount_like_amount_matches_difference'})

    return {
        'analyzed_difference_abs': money(abs_difference),
        'suspicious_amounts': suspicious_amounts,
        'possible_duplicate_lines': possible_duplicate_lines,
        'possible_missing_discount_application': possible_missing_discount_application,
        'amount_delta_candidates': amount_delta_candidates,
    }


def _line_as_rescue_candidate(line, reason: str) -> dict:
    amounts = AMOUNT_PATTERN.findall(line.normalized_line or '')
    return {
        'line_no': line.line_no,
        'raw_line': line.raw_line,
        'normalized_line': line.normalized_line,
        'line_type': line.line_type,
        'amounts': [normalize_decimal(amount) for amount in amounts],
        'reason': reason,
    }


def _is_rescue_product_name_line(line) -> bool:
    normalized = line.normalized_line or ''
    if not normalized:
        return False
    if line.line_type in RESCUE_EXCLUDED_LINE_TYPES:
        return False
    if AMOUNT_PATTERN.search(normalized):
        return False
    if not re.search(r'[A-Za-zÀ-ÿ]', normalized):
        return False
    if len(normalized.strip()) < 3:
        return False
    return True


def _is_rescue_amount_line(line) -> bool:
    normalized = line.normalized_line or ''
    if not normalized:
        return False
    if not AMOUNT_PATTERN.search(normalized):
        return False
    letters = re.findall(r'[A-Za-zÀ-ÿ]', normalized)
    alpha_text = ''.join(letters)
    return len(alpha_text) <= 3 or line.line_type in {'payment_line', 'total_line', 'unknown_line'}


def build_product_block_rescue_diagnostics(classified_lines: list) -> dict:
    orphan_product_name_lines = []
    orphan_amount_lines = []
    nearby_name_amount_pairs = []
    stop_line_no = None

    for line in classified_lines:
        if stop_line_no is None and line.line_type in RESCUE_STOP_LINE_TYPES and line.normalized_line:
            stop_line_no = line.line_no

        if _is_rescue_product_name_line(line):
            reason = 'text_without_amount_before_total_payment_vat_zone' if stop_line_no is None or line.line_no < stop_line_no else 'text_without_amount_after_total_payment_vat_zone'
            orphan_product_name_lines.append(_line_as_rescue_candidate(line, reason))

        if _is_rescue_amount_line(line):
            reason = 'standalone_amount_before_total_payment_vat_zone' if stop_line_no is None or line.line_no < stop_line_no else 'standalone_amount_in_or_after_total_payment_vat_zone'
            orphan_amount_lines.append(_line_as_rescue_candidate(line, reason))

    for name in orphan_product_name_lines:
        for amount in orphan_amount_lines:
            distance = int(amount['line_no']) - int(name['line_no'])
            if 1 <= abs(distance) <= 3:
                nearby_name_amount_pairs.append({
                    'product_name_line_no': name['line_no'],
                    'amount_line_no': amount['line_no'],
                    'distance': distance,
                    'product_name_raw_line': name['raw_line'],
                    'amount_raw_line': amount['raw_line'],
                    'amounts': amount['amounts'],
                    'reason': 'name_amount_within_3_lines',
                })

    before_stop_names = [line for line in orphan_product_name_lines if stop_line_no is None or line['line_no'] < stop_line_no]
    before_stop_pairs = [
        pair for pair in nearby_name_amount_pairs
        if stop_line_no is None or (pair['product_name_line_no'] < stop_line_no and pair['amount_line_no'] < stop_line_no)
    ]

    if before_stop_names:
        candidate_start = before_stop_names[0]['line_no']
        candidate_end = before_stop_names[-1]['line_no']
        reason = 'orphan_product_names_before_total_payment_vat_zone'
    elif before_stop_pairs:
        candidate_start = min(pair['product_name_line_no'] for pair in before_stop_pairs)
        candidate_end = max(pair['amount_line_no'] for pair in before_stop_pairs)
        reason = 'nearby_name_amount_pairs_before_total_payment_vat_zone'
    else:
        candidate_start = None
        candidate_end = None
        reason = 'no_rescue_product_block_candidate'

    return {
        'candidate_product_block_start': candidate_start,
        'candidate_product_block_end': candidate_end,
        'orphan_product_name_lines': orphan_product_name_lines,
        'orphan_amount_lines': orphan_amount_lines,
        'nearby_name_amount_pairs': nearby_name_amount_pairs,
        'product_block_rescue_reason': reason,
        'stop_line_no': stop_line_no,
        'stop_line_reason': 'first_total_payment_vat_line' if stop_line_no is not None else '',
    }


def _contains_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _is_name_amount_link_name_candidate(orphan_name: dict, stop_line_no: int | None, store_hint: str) -> tuple[bool, str]:
    line_no = int(orphan_name.get('line_no', 0))
    normalized = str(orphan_name.get('normalized_line') or '')
    lowered = normalized.lower()

    if stop_line_no is not None and line_no >= int(stop_line_no):
        return False, 'name_line_in_or_after_total_payment_vat_zone'
    if _contains_any_keyword(lowered, NAME_AMOUNT_LINK_HEADER_KEYWORDS):
        return False, 'name_line_matches_generic_header_or_metadata_keyword'
    if _contains_any_keyword(lowered, NAME_AMOUNT_LINK_STORE_HEADER_KEYWORDS.get(store_hint, ())):
        return False, 'name_line_matches_store_header_keyword'
    if len(re.findall(r'[A-Za-zÀ-ÿ]', normalized)) < 3:
        return False, 'name_line_has_too_little_alpha_text'
    return True, 'orphan_product_name_before_total_payment_vat_zone'


def _is_name_amount_link_amount_candidate(orphan_amount: dict, stop_line_no: int | None) -> tuple[bool, str]:
    line_no = int(orphan_amount.get('line_no', 0))
    line_type = str(orphan_amount.get('line_type') or '')
    amounts = orphan_amount.get('amounts') or []
    normalized = str(orphan_amount.get('normalized_line') or '')

    if not amounts:
        return False, 'amount_line_without_amount'
    if stop_line_no is not None and line_no >= int(stop_line_no):
        return False, 'amount_line_in_or_after_total_payment_vat_zone'
    if line_type in {'payment_line', 'total_line', 'vat_line', 'metadata_line'}:
        return False, 'amount_line_has_protected_line_type'
    if _contains_any_keyword(normalized, TOTAL_KEYWORDS + TOTAL_HINT_EXCLUDE_KEYWORDS):
        return False, 'amount_line_matches_total_keyword'
    return True, 'orphan_amount_before_total_payment_vat_zone'


def build_product_name_amount_link_diagnostics(product_block_rescue_diagnostics: dict, store_hint: str) -> dict:
    """Diagnose only: suggest possible orphan product-name/amount links without reconstructing rows."""
    stop_line_no = product_block_rescue_diagnostics.get('stop_line_no')
    orphan_names = product_block_rescue_diagnostics.get('orphan_product_name_lines') or []
    orphan_amounts = product_block_rescue_diagnostics.get('orphan_amount_lines') or []
    candidate_links = []
    rejected_links = []
    eligible_names = []
    eligible_amounts = []

    for name in orphan_names:
        accepted, reason = _is_name_amount_link_name_candidate(name, stop_line_no, store_hint)
        annotated = {**name, 'link_candidate_reason': reason}
        if accepted:
            eligible_names.append(annotated)
        else:
            rejected_links.append({
                'product_name_line_no': name.get('line_no'),
                'product_name_raw_line': name.get('raw_line'),
                'rejection_reason': reason,
            })

    for amount in orphan_amounts:
        accepted, reason = _is_name_amount_link_amount_candidate(amount, stop_line_no)
        annotated = {**amount, 'link_candidate_reason': reason}
        if accepted:
            eligible_amounts.append(annotated)
        else:
            rejected_links.append({
                'amount_line_no': amount.get('line_no'),
                'amount_raw_line': amount.get('raw_line'),
                'rejection_reason': reason,
            })

    for name in eligible_names:
        for amount in eligible_amounts:
            distance = int(amount['line_no']) - int(name['line_no'])
            if distance <= 0:
                rejected_links.append({
                    'product_name_line_no': name['line_no'],
                    'amount_line_no': amount['line_no'],
                    'distance': distance,
                    'product_name_raw_line': name['raw_line'],
                    'amount_raw_line': amount['raw_line'],
                    'rejection_reason': 'amount_not_after_product_name_line',
                })
                continue
            if distance > NAME_AMOUNT_LINK_MAX_DISTANCE:
                rejected_links.append({
                    'product_name_line_no': name['line_no'],
                    'amount_line_no': amount['line_no'],
                    'distance': distance,
                    'product_name_raw_line': name['raw_line'],
                    'amount_raw_line': amount['raw_line'],
                    'rejection_reason': 'line_distance_too_large_for_diagnostic_link',
                })
                continue
            candidate_links.append({
                'product_name_line_no': name['line_no'],
                'amount_line_no': amount['line_no'],
                'distance': distance,
                'product_name_raw_line': name['raw_line'],
                'amount_raw_line': amount['raw_line'],
                'amounts': amount.get('amounts', []),
                'diagnostic_reason': 'orphan_product_name_followed_by_orphan_amount_before_total_payment_vat_zone',
                'diagnostic_only': True,
            })

    return {
        'diagnostic_scope': 'orphan_product_name_to_orphan_amount_before_total_payment_vat_zone',
        'max_line_distance': NAME_AMOUNT_LINK_MAX_DISTANCE,
        'store_hint': store_hint,
        'candidate_link_count': len(candidate_links),
        'candidate_links': candidate_links,
        'eligible_name_line_count': len(eligible_names),
        'eligible_amount_line_count': len(eligible_amounts),
        'rejected_link_count': len(rejected_links),
        'rejected_links': rejected_links,
        'diagnostic_only': True,
        'reconstruction_applied': False,
    }


def _is_amount_only_currency_line(normalized_line: str) -> bool:
    if not normalized_line or not AMOUNT_PATTERN.search(normalized_line):
        return False
    remainder = AMOUNT_PATTERN.sub(' ', normalized_line)
    remainder = CURRENCY_WORDS_PATTERN.sub(' ', remainder)
    remainder = CURRENCY_SYMBOLS_PATTERN.sub(' ', remainder)
    remainder = re.sub(r'[\s\.,:;()\[\]{}+\-_/\\|]+', '', remainder)
    return remainder == ''


def exclude_amount_only_payment_zone_lines(classified_lines: list, product_block_rescue_diagnostics: dict) -> tuple[list, dict]:
    stop_line_no = product_block_rescue_diagnostics.get('stop_line_no')
    excluded_lines = []
    guarded_lines = []

    for line in classified_lines:
        normalized = line.normalized_line or ''
        in_or_after_payment_zone = stop_line_no is not None and int(line.line_no) >= int(stop_line_no)
        amount_only_currency = _is_amount_only_currency_line(normalized)
        has_real_article_text = bool(re.search(r'[A-Za-zÀ-ÿ]{4,}', normalized)) and not amount_only_currency

        if amount_only_currency and in_or_after_payment_zone and not has_real_article_text:
            excluded_lines.append({
                'line_no': line.line_no,
                'raw_line': line.raw_line,
                'normalized_line': normalized,
                'previous_line_type': line.line_type,
                'amounts': [normalize_decimal(amount) for amount in AMOUNT_PATTERN.findall(normalized)],
                'amount_only_exclusion_reason': 'amount_currency_only_in_or_after_payment_total_vat_zone',
            })
            guarded_lines.append(replace(line, line_type='unknown_line', reason='amount_only_payment_zone_excluded'))
        else:
            guarded_lines.append(line)

    return guarded_lines, {
        'excluded_amount_only_lines': excluded_lines,
        'excluded_amount_only_count': len(excluded_lines),
        'amount_only_exclusion_reason': 'amount_currency_only_in_or_after_payment_total_vat_zone',
    }


def _matched_loyalty_rules(normalized_line: str, store_hint: str) -> list[dict]:
    lowered = normalized_line.lower()
    matches = [
        {'scope': 'generic', 'keyword': keyword}
        for keyword in GENERIC_LOYALTY_KEYWORDS
        if keyword in lowered
    ]
    for keyword in STORE_LOYALTY_KEYWORDS.get(store_hint, ()): 
        if keyword in lowered:
            matches.append({'scope': f'store:{store_hint}', 'keyword': keyword})
    return matches


def exclude_loyalty_payment_zone_lines(classified_lines: list, product_block_rescue_diagnostics: dict, store_hint: str) -> tuple[list, dict]:
    stop_line_no = product_block_rescue_diagnostics.get('stop_line_no')
    excluded_lines = []
    guarded_lines = []

    for line in classified_lines:
        normalized = line.normalized_line or ''
        in_or_after_payment_zone = stop_line_no is not None and int(line.line_no) >= int(stop_line_no)
        matched_rules = _matched_loyalty_rules(normalized, store_hint)

        if in_or_after_payment_zone and matched_rules:
            excluded_lines.append({
                'line_no': line.line_no,
                'raw_line': line.raw_line,
                'normalized_line': normalized,
                'previous_line_type': line.line_type,
                'matched_loyalty_rule': matched_rules,
                'loyalty_exclusion_reason': 'loyalty_campaign_line_in_or_after_payment_total_vat_zone',
            })
            guarded_lines.append(replace(line, line_type='unknown_line', reason='loyalty_payment_zone_excluded'))
        else:
            guarded_lines.append(line)

    return guarded_lines, {
        'excluded_loyalty_lines': excluded_lines,
        'excluded_loyalty_count': len(excluded_lines),
        'loyalty_exclusion_reason': 'loyalty_campaign_line_in_or_after_payment_total_vat_zone',
    }


def compute_totals_diagnostics(rows: list[ReceiptLine], classified_lines: list, store_hint: str) -> dict:
    gross_sum = sum((to_decimal(row.line_total) for row in rows), Decimal('0'))
    discount_candidates = []
    total_candidates = []

    for line in classified_lines:
        normalized = line.normalized_line or ''
        lowered = normalized.lower()
        amounts = extract_amounts(normalized)
        if not amounts:
            continue
        last_amount = amounts[-1]
        if any(keyword in lowered for keyword in DISCOUNT_KEYWORDS):
            discount_candidates.append(_candidate(line, abs(last_amount), 'discount_keyword'))
        if any(keyword in lowered for keyword in TOTAL_KEYWORDS):
            total_candidates.append(_candidate(line, last_amount, 'total_keyword'))

    selected_total_hint, excluded_total_hints = select_total_hint(total_candidates)
    discount_total, selected_discount_strategy, selected_discount_candidates, excluded_discount_candidates = select_discount_total(discount_candidates)
    net_candidate = gross_sum - discount_total
    selected_total_amount = selected_total_hint.get('amount') if selected_total_hint else ''
    selected_total_decimal = to_decimal(selected_total_amount)
    difference = net_candidate - selected_total_decimal if selected_total_hint else net_candidate
    delta_diagnostics = build_delta_diagnostics(rows, classified_lines, difference)

    return {
        'store_hint': store_hint,
        'gross_line_sum': money(gross_sum),
        'discount_total_detected': money(discount_total),
        'net_total_candidate': money(net_candidate),
        'selected_total_hint': selected_total_hint,
        'selected_total_hint_reason': selected_total_hint.get('selected_total_hint_reason') if selected_total_hint else '',
        'net_vs_selected_total_difference': money(difference),
        'all_total_hints': total_candidates,
        'excluded_total_hints': excluded_total_hints,
        'selected_discount_strategy': selected_discount_strategy,
        'selected_discount_candidates': selected_discount_candidates,
        'excluded_discount_candidates': excluded_discount_candidates,
        'all_discount_candidates': discount_candidates,
        'discount_candidate_count': len(discount_candidates),
        'line_count_after_merge': len(rows),
        'totals_strategy': 'diagnostic_gross_minus_selected_discount_vs_selected_total_hint',
        'suspicious_amounts': delta_diagnostics['suspicious_amounts'],
        'possible_duplicate_lines': delta_diagnostics['possible_duplicate_lines'],
        'possible_missing_discount_application': delta_diagnostics['possible_missing_discount_application'],
        'amount_delta_candidates': delta_diagnostics['amount_delta_candidates'],
    }


def process_receipt(image_path: Path, output_dir: Path, lang: str):
    text = pytesseract.image_to_string(Image.open(image_path), lang=lang)

    store_hint = detect_store_hint(text, image_path.name)
    profile = get_profile_for_store(store_hint)

    classified_lines = classify_lines(text)
    classified_lines, refinement_diagnostics = profile.refine_classified_lines(classified_lines)
    pre_guard_rescue_diagnostics = build_product_block_rescue_diagnostics(classified_lines)
    classified_lines, amount_only_exclusion_diagnostics = exclude_amount_only_payment_zone_lines(
        classified_lines,
        pre_guard_rescue_diagnostics,
    )
    classified_lines, loyalty_exclusion_diagnostics = exclude_loyalty_payment_zone_lines(
        classified_lines,
        pre_guard_rescue_diagnostics,
        store_hint,
    )
    line_type_counts = summarize_line_types(classified_lines)

    product_block = profile.detect_product_block(classified_lines)
    product_block_rescue_diagnostics = build_product_block_rescue_diagnostics(classified_lines)
    product_name_amount_link_diagnostics = build_product_name_amount_link_diagnostics(
        product_block_rescue_diagnostics,
        store_hint,
    )

    rows = parse_receipt_lines(
        text,
        image_path.name,
        store_hint,
        profile.profile_name,
        classified_lines,
        product_block,
    )

    merged_rows, merge_diagnostics = profile.merge_quantity_lines(rows, classified_lines)
    totals_diagnostics = compute_totals_diagnostics(merged_rows, classified_lines, store_hint)

    metadata = {
        'source_file': image_path.name,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'store_hint': store_hint,
        'profile_name': profile.profile_name,
        'detected_rows': len(merged_rows),
        'line_type_counts': line_type_counts,
        'product_block': product_block,
        'product_block_rescue_diagnostics': product_block_rescue_diagnostics,
        'product_name_amount_link_diagnostics': product_name_amount_link_diagnostics,
        'amount_only_exclusion_diagnostics': amount_only_exclusion_diagnostics,
        'loyalty_exclusion_diagnostics': loyalty_exclusion_diagnostics,
        'merge_diagnostics': merge_diagnostics,
        'refinement_diagnostics': refinement_diagnostics,
        'totals_diagnostics': totals_diagnostics,
    }

    json_dir = output_dir / 'json'
    csv_dir = output_dir / 'per_receipt'
    json_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    json_payload = {
        'schema_version': 'receipt-ocr-poc-v15-name-amount-link-diagnostics',
        'metadata': metadata,
        'classified_lines': [asdict(line) for line in classified_lines],
        'lines': [asdict(row) for row in merged_rows],
    }

    (json_dir / f'{image_path.stem}.json').write_text(
        json.dumps(json_payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    pd.DataFrame([asdict(row) for row in merged_rows]).to_csv(
        csv_dir / f'{image_path.stem}.csv',
        index=False,
    )

    return merged_rows, ReceiptResult(
        source_file=image_path.name,
        run_result='success',
        store_hint=store_hint,
        profile_name=profile.profile_name,
        detected_rows=len(merged_rows),
        ignored_line_count=sum(v for k, v in line_type_counts.items() if k not in PARSEABLE_LINE_TYPES),
        line_type_counts=line_type_counts,
        merge_diagnostics=merge_diagnostics,
        refinement_diagnostics=refinement_diagnostics,
        totals_diagnostics=totals_diagnostics,
        product_block_rescue_diagnostics=product_block_rescue_diagnostics,
        product_name_amount_link_diagnostics=product_name_amount_link_diagnostics,
        amount_only_exclusion_diagnostics=amount_only_exclusion_diagnostics,
        loyalty_exclusion_diagnostics=loyalty_exclusion_diagnostics,
    )


def list_image_files(input_dir: Path):
    return sorted([p for p in input_dir.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS])


def write_benchmark_summary(output_dir: Path, report_rows: list[ReceiptResult]):
    summary = {
        'schema_version': 'receipt-ocr-benchmark-v15-name-amount-link-diagnostics',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'total_receipts': len(report_rows),
        'run_success_count': sum(1 for row in report_rows if row.run_result == 'success'),
        'run_error_count': sum(1 for row in report_rows if row.run_result == 'error'),
        'total_detected_rows': sum(row.detected_rows for row in report_rows),
        'profiles_used': {},
        'merge_diagnostics': {},
        'refinement_diagnostics': {},
        'totals_diagnostics': {},
        'product_block_rescue_diagnostics': {},
        'product_name_amount_link_diagnostics': {},
        'amount_only_exclusion_diagnostics': {},
        'loyalty_exclusion_diagnostics': {},
    }

    for row in report_rows:
        summary['profiles_used'][row.source_file] = row.profile_name
        summary['merge_diagnostics'][row.source_file] = row.merge_diagnostics
        summary['refinement_diagnostics'][row.source_file] = row.refinement_diagnostics
        summary['totals_diagnostics'][row.source_file] = row.totals_diagnostics
        summary['product_block_rescue_diagnostics'][row.source_file] = row.product_block_rescue_diagnostics
        summary['product_name_amount_link_diagnostics'][row.source_file] = row.product_name_amount_link_diagnostics
        summary['amount_only_exclusion_diagnostics'][row.source_file] = row.amount_only_exclusion_diagnostics
        summary['loyalty_exclusion_diagnostics'][row.source_file] = row.loyalty_exclusion_diagnostics

    (output_dir / 'benchmark_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='input_receipts')
    parser.add_argument('--output', default='output_csv')
    parser.add_argument('--lang', default='nld+eng')
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    report_rows = []

    for image_file in list_image_files(input_dir):
        try:
            rows, result = process_receipt(image_file, output_dir, args.lang)
            all_rows.extend(rows)
            report_rows.append(result)
            refined = result.refinement_diagnostics.get('refined_lines_count', 0)
            merged = result.merge_diagnostics.get('merged_quantity_lines_count', 0)
            excluded_amount_only = result.amount_only_exclusion_diagnostics.get('excluded_amount_only_count', 0)
            excluded_loyalty = result.loyalty_exclusion_diagnostics.get('excluded_loyalty_count', 0)
            link_candidates = result.product_name_amount_link_diagnostics.get('candidate_link_count', 0)
            gross = result.totals_diagnostics.get('gross_line_sum', '0.00')
            net = result.totals_diagnostics.get('net_total_candidate', '0.00')
            selected_total = result.totals_diagnostics.get('selected_total_hint') or {}
            selected_total_amount = selected_total.get('amount', '')
            diff = result.totals_diagnostics.get('net_vs_selected_total_difference', '')
            rescue = result.product_block_rescue_diagnostics.get('product_block_rescue_reason', '')
            print(f'[OK] {image_file.name}: {len(rows)} rows refined={refined} merged={merged} excluded_amount_only={excluded_amount_only} excluded_loyalty={excluded_loyalty} name_amount_links={link_candidates} gross={gross} net={net} selected_total={selected_total_amount} diff={diff} rescue={rescue} profile={result.profile_name}')
        except Exception as exc:
            print(f'[ERROR] {image_file.name}: {exc}')

    pd.DataFrame([asdict(row) for row in all_rows]).to_csv(output_dir / 'combined_receipts.csv', index=False)
    pd.DataFrame([asdict(row) for row in report_rows]).to_csv(output_dir / 'processing_report.csv', index=False)
    write_benchmark_summary(output_dir, report_rows)

    print(f'Output: {output_dir}')


if __name__ == '__main__':
    main()
