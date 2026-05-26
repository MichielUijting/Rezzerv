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
AH_SAVINGS_STAMPS_RE = re.compile(r'^(?:(?P<qty>\d+)\s+)?koopzegels(?:\s+premium)?\s+(?P<amount>\d{1,5}(?:[\.,]\d{2}))$', re.I)
AH_SAVINGS_STAMPS_LABEL_RE = re.compile(r'^(?:(?P<qty>\d+)\s+)?koopzegels(?:\s+premium)?$', re.I)
AMOUNT_ONLY_RE = re.compile(r'^(?P<amount>\d{1,5}(?:[\.,]\d{2}))$')
POSITIVE_CONTRIBUTOR_BRANCH = 'positive_savings_contribution'
AH_CANDIDATE_SELECTION_BRANCH = 'ah_candidate_selection_ssot_safe'


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
    if any('koopzegels premium' in str(line or '').lower() for line in text_lines):
        return True
    return False




def _ah_candidate_selection_reason(line: str | None) -> dict[str, Any]:
    """SSOT-safe AH line selection helper.

    This helper only marks AH product/non-product candidate evidence. It must never set
    receipt status, parser status, po_norm_status_label, or UI category fields.
    """
    raw = str(line or '').strip()
    norm = _norm(raw)
    non_product_reasons: list[str] = []

    if not raw:
        return {
            'ah_candidate_selection_branch': AH_CANDIDATE_SELECTION_BRANCH,
            'is_ah_product_candidate': False,
            'is_ah_non_product_candidate': False,
            'ah_candidate_reasons': [],
            'ah_non_product_reasons': ['empty_line'],
        }

    if any(token in norm for token in ('subtotaal', 'totaal', 'te betalen', 'betalen')):
        non_product_reasons.append('ah_total_or_payment_total_line')
    if any(token in norm for token in ('pinnen', 'pin ', 'v pay', 'v-pay', 'betaling', 'betaald met')):
        non_product_reasons.append('ah_payment_line')
    if any(token in norm for token in ('app deals', 'bonus', 'voordeel', 'korting')):
        non_product_reasons.append('ah_promotion_or_advantage_line')
    if any(token in norm for token in ('btw', 'over', 'eur')) and len(_extract_amounts(raw)) >= 2:
        non_product_reasons.append('ah_vat_or_tax_line')
    if any(token in norm for token in ('terminal', 'merchant', 'transactie', 'kaart', 'autorisatiecode', 'klantticket', 'poi:')):
        non_product_reasons.append('ah_payment_terminal_metadata')
    if any(token in norm for token in ('download nu de ah', 'spaar automatisch', 'gratis een product')):
        non_product_reasons.append('ah_footer_marketing_line')

    amounts = _extract_amounts(raw)
    has_amount = bool(amounts)
    has_letters = any(ch.isalpha() for ch in raw)
    has_non_product_reason = bool(non_product_reasons)
    is_product = has_amount and has_letters and not has_non_product_reason

    reasons: list[str] = []
    if is_product:
        reasons.append('ah_amount_bearing_text_line_without_non_product_signal')

    return {
        'ah_candidate_selection_branch': AH_CANDIDATE_SELECTION_BRANCH,
        'is_ah_product_candidate': is_product,
        'is_ah_non_product_candidate': has_non_product_reason,
        'ah_candidate_reasons': reasons,
        'ah_non_product_reasons': sorted(set(non_product_reasons)),
    }


def enrich_ah_amount_line_candidates(candidates: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return AH candidate evidence without changing receipt status or generic parser output."""
    enriched: list[dict[str, Any]] = []
    for candidate in candidates or []:
        item = dict(candidate)
        line = item.get('normalized_line') or item.get('raw_line') or ''
        item.update(_ah_candidate_selection_reason(line))
        item['status_classification_applied'] = False
        item['po_norm_status_label_touched'] = False
        enriched.append(item)
    return enriched

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


def _positive_contributor_line(*, quantity: Decimal, line_total: Decimal, source_index: int, raw_line: str | None, normalized_line: str | None, filename: str | None, store_name: str | None, hint: str) -> dict[str, Any] | None:
    if quantity <= 0 or line_total <= Decimal('0.00'):
        return None
    try:
        unit_price = (line_total / quantity).quantize(Decimal('0.01'))
    except Exception:
        unit_price = line_total
    amount_label = str(line_total).replace('.', ',')
    label = f'KOOPZEGELS PREMIUM {amount_label}'
    return {
        'raw_label': label,
        'normalized_label': label,
        'quantity': float(quantity),
        'unit': None,
        'unit_price': float(unit_price),
        'line_total': float(line_total),
        'discount_amount': None,
        'barcode': None,
        'confidence_score': 0.94,
        'source_index': source_index,
        'producer_trace': {
            'filename': filename,
            'store_name': store_name,
            'profile': 'ah',
            'profile_hook': 'positive_contributors',
            'function_name': 'extract_positive_contributors',
            'append_branch': POSITIVE_CONTRIBUTOR_BRANCH,
            'parser_path': 'AhReceiptProfile.runtime.positive_contributors.koopzegels_premium',
            'source_index': source_index,
            'raw_line': raw_line,
            'normalized_line': normalized_line,
            'label': 'KOOPZEGELS PREMIUM',
            'display_label': 'KOOPZEGELS PREMIUM',
            'quantity': float(quantity),
            'unit_price': float(unit_price),
            'amount': float(line_total),
            'classification': 'product_candidate',
            'classification_allows_append': True,
            'append_allowed': True,
            'caller_line_hint': hint,
            'contributor_type': 'positive_total_contributor',
            'inventory_article': False,
            'status_neutral': True,
        },
    }


def _positive_contributor_from_line(line: str, *, source_index: int, following_lines: list[str], filename: str | None, store_name: str | None) -> dict[str, Any] | None:
    normalized = _norm(line)
    match = AH_SAVINGS_STAMPS_RE.match(normalized.lower())
    if match:
        try:
            quantity = Decimal(match.group('qty') or '1').quantize(Decimal('1'))
            line_total = Decimal(match.group('amount').replace(',', '.')).quantize(Decimal('0.01'))
        except Exception:
            return None
        return _positive_contributor_line(quantity=quantity, line_total=line_total, source_index=source_index, raw_line=line, normalized_line=normalized, filename=filename, store_name=store_name, hint='R9-32E AH positive_contributors same-line KOOPZEGELS PREMIUM')
    label_match = AH_SAVINGS_STAMPS_LABEL_RE.match(normalized.lower())
    if not label_match:
        return None
    quantity = Decimal(label_match.group('qty') or '1').quantize(Decimal('1'))
    for next_line in following_lines[:2]:
        next_normalized = _norm(next_line)
        amount_match = AMOUNT_ONLY_RE.match(next_normalized)
        if not amount_match:
            continue
        try:
            line_total = Decimal(amount_match.group('amount').replace(',', '.')).quantize(Decimal('0.01'))
        except Exception:
            continue
        return _positive_contributor_line(quantity=quantity, line_total=line_total, source_index=source_index, raw_line=line, normalized_line=normalized, filename=filename, store_name=store_name, hint='R9-32E AH positive_contributors adjacent-amount KOOPZEGELS PREMIUM')
    return None


def extract_positive_contributors(text_lines: list[str], existing_lines: list[dict[str, Any]], *, store_name: str | None, filename: str | None) -> list[dict[str, Any]]:
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
    generated = []
    for source_index, raw_line in enumerate(text_lines):
        candidate = _positive_contributor_from_line(raw_line, source_index=source_index, following_lines=text_lines[source_index + 1:source_index + 3], filename=filename, store_name=store_name)
        if not candidate:
            continue
        try:
            candidate_key = _key(str(candidate.get('raw_label') or ''), Decimal(str(candidate.get('line_total'))).quantize(Decimal('0.01')))
        except Exception:
            candidate_key = _key(str(candidate.get('raw_label') or ''), None)
        if candidate_key in existing_keys:
            continue
        generated.append(candidate)
        existing_keys.add(candidate_key)
    return generated


def _build_savings_stamps_candidate(quantity: Decimal, line_total: Decimal, *, hint: str) -> dict[str, Any] | None:
    if quantity <= 0 or line_total <= Decimal('0.00'):
        return None
    try:
        unit_price = (line_total / quantity).quantize(Decimal('0.01'))
    except Exception:
        unit_price = line_total
    amount_label = str(line_total).replace('.', ',')
    return {
        'label': f'KOOPZEGELS PREMIUM {amount_label}',
        'quantity': float(quantity),
        'unit': None,
        'unit_price': unit_price,
        'line_total': line_total,
        'append_branch': 'ah_koopzegels_premium_detected',
        'parser_path': 'AhReceiptProfile.runtime.savings_stamps_positive_contributor',
        'caller_line_hint': hint,
        'confidence_score': 0.91,
    }


def _parse_ah_savings_stamps_line(line: str) -> dict[str, Any] | None:
    normalized = _norm(line)
    match = AH_SAVINGS_STAMPS_RE.match(normalized.lower())
    if not match:
        return None
    try:
        quantity = Decimal(match.group('qty') or '1').quantize(Decimal('1'))
        line_total = Decimal(match.group('amount').replace(',', '.')).quantize(Decimal('0.01'))
    except Exception:
        return None
    return _build_savings_stamps_candidate(
        quantity,
        line_total,
        hint='R9-32B AH koopzegels same-line positive total contributor',
    )


def _parse_ah_savings_stamps_adjacent_amount_line(line: str, following_lines: list[str]) -> dict[str, Any] | None:
    normalized = _norm(line)
    match = AH_SAVINGS_STAMPS_LABEL_RE.match(normalized.lower())
    if not match:
        return None
    quantity = Decimal(match.group('qty') or '1').quantize(Decimal('1'))
    for next_line in following_lines[:2]:
        next_normalized = _norm(next_line)
        amount_match = AMOUNT_ONLY_RE.match(next_normalized)
        if not amount_match:
            continue
        try:
            line_total = Decimal(amount_match.group('amount').replace(',', '.')).quantize(Decimal('0.01'))
        except Exception:
            continue
        return _build_savings_stamps_candidate(
            quantity,
            line_total,
            hint='R9-32B AH koopzegels adjacent-amount positive total contributor',
        )
    return None


def _parse_ah_article_line(line: str) -> dict[str, Any] | None:
    normalized = _norm(line)
    lowered = normalized.lower()
    if not normalized or not re.search(r'[a-zA-Z]', normalized):
        return None
    if any(token in lowered for token in HARD_NON_ARTICLE_TOKENS):
        return None
    if any(token in lowered for token in DISCOUNT_TOKENS):
        return None
    if 'koopzegels' in lowered:
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
        text_without_last_amount = normalized
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

    generated: list[dict[str, Any]] = extract_positive_contributors(
        text_lines,
        existing_lines,
        store_name=store_name,
        filename=filename,
    )
    for source_index, raw_line in enumerate(text_lines):
        parsed = _parse_ah_article_line(raw_line)
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