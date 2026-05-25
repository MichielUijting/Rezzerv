from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Callable


AMOUNT2_RE = re.compile(r'(?<!\d)(-?\d{1,5}(?:[\.,]\d{2}))(?!\d)')
AMOUNT1_RE = re.compile(r'(?<!\d)(-?\d{1,5}(?:[\.,]\d{1}))(?!\d)')

HARD_NON_ARTICLE_TOKENS = (
    'totaal', 'te betalen', 'subtotaal', 'betaling', 'betaald', 'bankpas', 'pin',
    'maestro', 'visa', 'btw', 'wisselgeld', 'terminal', 'transactie', 'kaart',
    'filiaal', 'kassa', 'bonnr', 'klantenservice', 'www.', 'ah.nl', 'bedankt'
)

DISCOUNT_TOKENS = ('bonus', 'korting', 'persoonlijke bonus', 'bonus box', 'uw voordeel')
AH_SAVINGS_STAMPS_RE = re.compile(r'^(?P<qty>\d+)\s+koopzegels(?:\s+premium)?\s+(?P<amount>\d{1,5}(?:[\.,]\d{2}))$', re.I)


def _norm(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _key(label: str, line_total: Decimal | None) -> tuple[str, str]:
    normalized_label = re.sub(r'[^a-z0-9]+', '', str(label or '').lower())
    amount = str(line_total.quantize(Decimal('0.01'))) if line_total is not None else ''
    return normalized_label, amount


def _looks_like_ah_context(store_name: str | None, text_lines: list[str]) -> bool:
    store = str(store_name or '').strip().lower()
    if store == 'albert heijn':
        return True
    haystack = ' '.join(text_lines[:20]).lower()
    if 'albert heijn' in haystack:
        return True
    if re.search(r'\bah\b', haystack) and any(token in haystack for token in ('bonus', 'totaal', 'betaling', 'kassabon')):
        return True
    return False


def _extract_amounts(line: str) -> list[Decimal]:
    values: list[Decimal] = []
    for raw in AMOUNT2_RE.findall(line):
        try:
            values.append(Decimal(raw.replace(',', '.')).quantize(Decimal('0.01')))
        except Exception:
            pass
    if not values:
        for raw in AMOUNT1_RE.findall(line):
            try:
                values.append(Decimal(raw.replace(',', '.') + '0').quantize(Decimal('0.01')))
            except Exception:
                pass
    return values


def _parse_ah_savings_stamps_line(line: str) -> dict[str, Any] | None:
    normalized = _norm(line)
    match = AH_SAVINGS_STAMPS_RE.match(normalized.lower())
    if not match:
        return None
    try:
        quantity = Decimal(match.group('qty')).quantize(Decimal('1'))
        line_total = Decimal(match.group('amount').replace(',', '.')).quantize(Decimal('0.01'))
    except Exception:
        return None
    if quantity <= 0 or line_total <= Decimal('0.00'):
        return None
    try:
        unit_price = (line_total / quantity).quantize(Decimal('0.01'))
    except Exception:
        unit_price = line_total
    return {
        'label': 'KOOPZEGELS PREMIUM',
        'quantity': float(quantity),
        'unit': None,
        'unit_price': unit_price,
        'line_total': line_total,
        'append_branch': 'ah_koopzegels_premium_detected',
        'parser_path': 'AhReceiptProfile.runtime.savings_stamps_positive_contributor',
        'caller_line_hint': 'R9-31C AH koopzegels positive total contributor',
        'confidence_score': 0.91,
    }


def _parse_ah_article_line(line: str) -> dict[str, Any] | None:
    normalized = _norm(line)
    lowered = normalized.lower()
    if not normalized or not re.search(r'[a-zA-Z]', normalized):
        return None
    if any(token in lowered for token in HARD_NON_ARTICLE_TOKENS):
        return None
    if any(token in lowered for token in DISCOUNT_TOKENS):
        return None

    amounts = _extract_amounts(normalized)
    if not amounts:
        return None
    line_total = amounts[-1]
    if line_total <= Decimal('0.00'):
        return None

    text_without_last_amount = AMOUNT2_RE.sub('', normalized, count=0)
    if amounts and len(amounts) == 1 and AMOUNT1_RE.search(normalized) and not AMOUNT2_RE.search(normalized):
        text_without_last_amount = AMOUNT1_RE.sub('', normalized, count=1)
    else:
        last_amount = re.escape(str(amounts[-1]).replace('.', ','))
        text_without_last_amount = normalized
        # Remove the textual last amount conservatively by cutting at the last occurrence of an amount pattern.
        matches = list(AMOUNT2_RE.finditer(normalized))
        if matches:
            last = matches[-1]
            text_without_last_amount = (normalized[:last.start()] + normalized[last.end():]).strip()

    match = re.match(r'^(?P<qty>\d+(?:[\.,]\d+)?(?:\s*kg)?)\s+(?P<label>.+)$', text_without_last_amount.strip(), re.I)
    quantity = Decimal('1.00')
    unit = None
    label = text_without_last_amount.strip()
    if match:
        qty_raw = match.group('qty').replace(',', '.')
        label = match.group('label').strip()
        if 'kg' in qty_raw.lower():
            unit = 'kg'
            qty_raw = qty_raw.lower().replace('kg', '').strip()
        try:
            quantity = Decimal(qty_raw).quantize(Decimal('0.001'))
        except Exception:
            quantity = Decimal('1.00')

    label = re.sub(r'\s+', ' ', label).strip(' .:-')
    # Remove unit price when line shape is qty label unitprice total, e.g. 2 AH CHIPS 0,39 1.17.
    embedded_amounts = AMOUNT2_RE.findall(label)
    if embedded_amounts:
        label = AMOUNT2_RE.sub('', label).strip(' .:-')
    if not label or not re.search(r'[A-Za-z]', label):
        return None
    if len(label) < 2 or len(label.split()) > 8:
        return None

    unit_price = line_total
    if quantity and quantity > 0:
        try:
            unit_price = (line_total / quantity).quantize(Decimal('0.01'))
        except Exception:
            unit_price = line_total

    return {
        'label': label,
        'quantity': float(quantity),
        'unit': unit,
        'unit_price': unit_price,
        'line_total': line_total,
    }


def build_ah_profile_article_lines(
    text_lines: list[str],
    existing_lines: list[dict[str, Any]],
    *,
    store_name: str | None,
    filename: str | None,
    append_product_candidate: Callable[..., Any],
    clean_label: Callable[[str | None], str],
    parse_quantity: Callable[[str | None], Any],
    parse_decimal: Callable[[str | None], Any],
    amount_to_float: Callable[[Any], Any],
    classify_line: Callable[[str], str],
    is_invalid_label: Callable[[str | None], bool],
) -> list[dict[str, Any]]:
    if not _looks_like_ah_context(store_name, text_lines):
        return []

    existing_keys = set()
    for line in existing_lines or []:
        raw_label = str(line.get('raw_label') or line.get('normalized_label') or '')
        line_total = None
        try:
            if line.get('line_total') is not None:
                line_total = Decimal(str(line.get('line_total'))).quantize(Decimal('0.01'))
        except Exception:
            line_total = None
        existing_keys.add(_key(raw_label, line_total))

    generated: list[dict[str, Any]] = []
    for source_index, raw_line in enumerate(text_lines):
        parsed = _parse_ah_savings_stamps_line(raw_line) or _parse_ah_article_line(raw_line)
        if not parsed:
            continue
        candidate_key = _key(str(parsed['label']), parsed['line_total'])
        if candidate_key in existing_keys:
            continue
        append_product_candidate(
            generated,
            label=str(parsed['label']),
            qty_raw=str(parsed['quantity']),
            amount1_raw=str(parsed['unit_price']),
            amount2_raw=str(parsed['line_total']),
            source_index=source_index,
            raw_line=raw_line,
            normalized_line=_norm(raw_line),
            filename=filename,
            store_name=store_name,
            function_name='build_ah_profile_article_lines',
            append_branch=str(parsed.get('append_branch') or 'ah_profile_safe_article_line'),
            parser_path=str(parsed.get('parser_path') or 'AhReceiptProfile.runtime.safe_article_line'),
            caller_line_hint=str(parsed.get('caller_line_hint') or 'R9-31B AH profile safe article construction'),
            clean_label=clean_label,
            parse_quantity=parse_quantity,
            parse_decimal=parse_decimal,
            amount_to_float=amount_to_float,
            classify_line=classify_line,
            is_invalid_label=is_invalid_label,
            confidence_score=float(parsed.get('confidence_score') or 0.82),
        )
        existing_keys.add(candidate_key)
    return generated
