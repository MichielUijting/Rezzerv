from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

_AMOUNT_TOKEN_RE = re.compile(r'[€£CE]?-?\d{1,6}(?:[\.,]\d{2})(?:\s*EUR)?', re.IGNORECASE)
_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
_PLUS_STORE_TOKENS = ('plus',)
_PLUSPUNTEN_TOKENS = ('pluspunten', 'piuspunten')
_SUBTOTAL_TOKENS = ('subtotaal',)
_TOTAL_TOKENS = ('totaal',)
_DISCOUNT_CONTEXT_TOKENS = ('plus geeft', 'voordeel', 'korting')
_CORRECTION_TOKENS = ('zegel', 'actie', 'pluspunten', 'piuspunten')


def _money(value: Any) -> Decimal:
    if value is None or value == '':
        return Decimal('0.00')
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _norm(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _norm_key(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower()).strip()


def _parse_amount_token(token: str) -> Decimal | None:
    raw = _norm(token).upper().replace('EUR', '').replace('€', '').replace('£', '').strip()
    sign = Decimal('-1') if raw.startswith('C-') or raw.startswith('E-') or raw.startswith('-') else Decimal('1')
    raw = raw.replace('C-', '').replace('E-', '').replace('C', '').replace('E', '').replace('-', '').replace(',', '.')
    try:
        return (Decimal(raw) * sign).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def _amounts_from_line(line: str) -> list[Decimal]:
    values: list[Decimal] = []
    for token in _AMOUNT_TOKEN_RE.findall(line or ''):
        value = _parse_amount_token(token)
        if value is not None:
            values.append(value)
    return values


def _looks_like_plus_image_context(text_lines: list[str], store_name: str | None, filename: str | None) -> bool:
    suffix = Path(filename or '').suffix.lower()
    if suffix not in _IMAGE_EXTENSIONS:
        return False
    haystack = ' '.join([str(store_name or ''), *(str(line or '') for line in text_lines[:20])]).lower()
    return any(token in haystack for token in _PLUS_STORE_TOKENS)


def _is_correction_window_line(line: str) -> bool:
    lowered = line.lower()
    return any(token in lowered for token in _CORRECTION_TOKENS)


def _classify_receipt_level_correction(line: str) -> Decimal | None:
    lowered = line.lower()
    if not _is_correction_window_line(line):
        return None
    amounts = _amounts_from_line(line)
    if not amounts:
        return None
    amount = amounts[-1]
    # PLUSPunten wins over ZEGEL: the line can contain both words, but points are a positive credit.
    if any(token in lowered for token in _PLUSPUNTEN_TOKENS):
        return abs(amount)
    if 'zegel' in lowered or 'actie' in lowered:
        return -abs(amount)
    return amount


def _subtotal_index(text_lines: list[str]) -> int | None:
    for index, line in enumerate(text_lines):
        lowered = str(line or '').lower()
        if any(token in lowered for token in _SUBTOTAL_TOKENS):
            return index
    return None


def _total_index_after(text_lines: list[str], subtotal_index: int) -> int | None:
    for index in range(subtotal_index + 1, len(text_lines)):
        lowered = str(text_lines[index] or '').lower()
        if any(token in lowered for token in _TOTAL_TOKENS):
            return index
    return None


def _subtotal_total_window(text_lines: list[str]) -> list[str]:
    subtotal_index = _subtotal_index(text_lines)
    if subtotal_index is None:
        return []
    total_index = _total_index_after(text_lines, subtotal_index)
    if total_index is None or total_index <= subtotal_index:
        return []
    return text_lines[subtotal_index + 1:total_index]


def _explicit_subtotal_total_amounts(text_lines: list[str]) -> tuple[Decimal | None, Decimal | None]:
    subtotal_index = _subtotal_index(text_lines)
    if subtotal_index is None:
        return None, None
    subtotal_amounts = _amounts_from_line(str(text_lines[subtotal_index] or ''))
    subtotal_amount = subtotal_amounts[-1] if subtotal_amounts else None
    total_amount = None
    total_index = _total_index_after(text_lines, subtotal_index)
    if total_index is not None:
        for line in text_lines[total_index: min(len(text_lines), total_index + 3)]:
            amounts = _amounts_from_line(str(line or ''))
            if amounts:
                total_amount = amounts[-1]
                break
    return subtotal_amount, total_amount


def _label_without_amount(line: str) -> str:
    label = _AMOUNT_TOKEN_RE.sub('', str(line or '')).strip()
    label = re.sub(r'\b\d+(?:[\.,]\d+)?\s*[xX]\b', '', label)
    return _norm(label).strip(' .:-')


def _best_line_match(lines: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    label_key = _norm_key(label)
    if not label_key:
        return None
    best: tuple[int, dict[str, Any]] | None = None
    label_tokens = set(label_key.split())
    for line in lines:
        candidate = str(line.get('raw_label') or line.get('normalized_label') or '')
        candidate_key = _norm_key(candidate)
        if not candidate_key:
            continue
        candidate_tokens = set(candidate_key.split())
        overlap = len(label_tokens & candidate_tokens)
        if not overlap:
            continue
        score = overlap * 10
        if label_key in candidate_key or candidate_key in label_key:
            score += 100
        if best is None or score > best[0]:
            best = (score, line)
    return best[1] if best else None


def _apply_plus_line_discounts(text_lines: list[str], lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adjusted = [dict(line) for line in lines]
    previous_article_line: str | None = None
    for raw_line in text_lines:
        line = _norm(raw_line)
        lowered = line.lower()
        amounts = _amounts_from_line(line)
        if any(token in lowered for token in _DISCOUNT_CONTEXT_TOKENS) and amounts:
            discount_amount = amounts[-1]
            if discount_amount >= 0 or previous_article_line is None:
                continue
            label = _label_without_amount(previous_article_line)
            target = _best_line_match(adjusted, label)
            if target is None:
                continue
            current_discount = _money(target.get('discount_amount'))
            if current_discount == Decimal('0.00'):
                target['discount_amount'] = float(discount_amount)
            continue
        if amounts and not any(token in lowered for token in _SUBTOTAL_TOKENS + _TOTAL_TOKENS + _CORRECTION_TOKENS + _DISCOUNT_CONTEXT_TOKENS):
            previous_article_line = line
    return adjusted


def _receipt_level_correction_total(text_lines: list[str]) -> Decimal | None:
    window = _subtotal_total_window(text_lines)
    if not window:
        return None
    total = Decimal('0.00')
    found = False
    for line in window:
        amount = _classify_receipt_level_correction(line)
        if amount is None:
            continue
        found = True
        total += amount
    return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if found else None


def _pluspunten_norm_line_candidate(text_lines: list[str], lines: list[dict[str, Any]]) -> tuple[dict[str, Any], Decimal] | None:
    """Return a validated PLUSPunten/zegel norm line for PLUS photo baselines.

    R9-38B15: some PO baselines count the PLUSPunten/zegel value as a norm
    line instead of a receipt-level correction. We only create that line when
    the product-line sum equals the explicit subtotal and adding the PLUSPunten
    value equals the explicit receipt total. This avoids double counting and
    avoids changing unrelated PLUS correction flows.
    """
    subtotal_amount, total_amount = _explicit_subtotal_total_amounts(text_lines)
    if subtotal_amount is None or total_amount is None:
        return None
    window = _subtotal_total_window(text_lines)
    if not window:
        return None
    plus_line_index: int | None = None
    plus_line: str | None = None
    plus_amount: Decimal | None = None
    subtotal_index = _subtotal_index(text_lines) or 0
    for offset, raw_line in enumerate(window, start=subtotal_index + 1):
        line = _norm(raw_line)
        lowered = line.lower()
        if not any(token in lowered for token in _PLUSPUNTEN_TOKENS):
            continue
        amounts = _amounts_from_line(line)
        if not amounts:
            continue
        plus_line_index = offset
        plus_line = line
        plus_amount = abs(amounts[-1])
        break
    if plus_line_index is None or plus_line is None or plus_amount is None:
        return None
    article_sum = sum((_money(line.get('line_total')) + _money(line.get('discount_amount')) for line in lines), Decimal('0.00')).quantize(Decimal('0.01'))
    if abs(article_sum - subtotal_amount) > Decimal('0.02'):
        return None
    if abs((article_sum + plus_amount) - total_amount) > Decimal('0.02'):
        return None
    if any(any(token in _norm_key(line.get('raw_label') or line.get('normalized_label')) for token in _PLUSPUNTEN_TOKENS) for line in lines):
        return None
    label = _label_without_amount(plus_line)
    label = re.sub(r'^[^A-Za-z0-9]+', '', label).strip(' .:-') or 'PLUSPunten DIGITAAL'
    norm_line = {
        'raw_label': label,
        'normalized_label': label,
        'quantity': None,
        'unit': None,
        'unit_price': float(plus_amount),
        'line_total': float(plus_amount),
        'discount_amount': None,
        'barcode': None,
        'confidence_score': 0.85,
        'source_index': plus_line_index,
        'producer_trace': {
            'filename': None,
            'store_name': 'PLUS',
            'function_name': '_extract_savings_action_lines',
            'append_branch': 'savings_action_line',
            'parser_path': 'r9_38b15.pluspunten_norm_line',
            'source_index': plus_line_index,
            'raw_line': plus_line,
            'normalized_line': plus_line,
            'label': label,
            'raw_label': label,
            'amount': float(plus_amount),
            'classification': 'validated_savings_action_line',
            'classification_allows_append': True,
            'append_allowed': True,
            'caller_line_hint': 'R9-38B15 PLUSPunten baseline norm line',
            'validated_savings_action_path': True,
        },
    }
    return norm_line, plus_amount


def apply_plus_runtime_corrections(
    *,
    text_lines: list[str],
    lines: list[dict[str, Any]],
    discount_total: Decimal | None,
    store_name: str | None,
    filename: str | None,
) -> tuple[list[dict[str, Any]], Decimal | None, dict[str, Any] | None]:
    if not _looks_like_plus_image_context(text_lines, store_name, filename):
        return lines, discount_total, None
    corrected_lines = _apply_plus_line_discounts(text_lines, lines)
    receipt_correction_total = _receipt_level_correction_total(text_lines)
    norm_line_candidate = _pluspunten_norm_line_candidate(text_lines, corrected_lines)
    if norm_line_candidate is not None:
        norm_line, plus_amount = norm_line_candidate
        norm_line['producer_trace']['filename'] = filename
        corrected_lines = [*corrected_lines, norm_line]
        remaining_receipt_correction = None
        if receipt_correction_total is not None:
            remaining = (receipt_correction_total - plus_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            remaining_receipt_correction = remaining if remaining != Decimal('0.00') else None
        diagnostics = {
            'r9_38b15_pluspunten_norm_line': {
                'applied': True,
                'pluspunten_as_norm_line_amount': float(plus_amount),
                'receipt_level_correction_total_before_norm_line': float(receipt_correction_total or Decimal('0.00')),
                'receipt_level_correction_total_after_norm_line': float(remaining_receipt_correction or Decimal('0.00')),
                'double_counting_prevented': True,
                'scope': 'PLUS image receipts only',
            }
        }
        return corrected_lines, remaining_receipt_correction, diagnostics
    if receipt_correction_total is None:
        return corrected_lines, discount_total, {
            'r9_38b9_plus_corrections': {
                'applied': corrected_lines != lines,
                'receipt_level_correction_total': None,
                'reason': 'no_subtotal_total_correction_window',
            }
        }
    diagnostics = {
        'r9_38b9_plus_corrections': {
            'applied': True,
            'line_discount_delta': float(
                sum((_money(line.get('discount_amount')) for line in corrected_lines), Decimal('0.00'))
                - sum((_money(line.get('discount_amount')) for line in lines), Decimal('0.00'))
            ),
            'receipt_level_correction_total': float(receipt_correction_total),
            'pluspunten_precedence': True,
            'subtotal_action_zegel_as_receipt_level_corrections': True,
            'status_neutral': False,
            'scope': 'PLUS image receipts only',
        }
    }
    return corrected_lines, receipt_correction_total, diagnostics
