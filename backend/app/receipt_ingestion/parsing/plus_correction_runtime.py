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


def _subtotal_total_window(text_lines: list[str]) -> list[str]:
    subtotal_index: int | None = None
    for index, line in enumerate(text_lines):
        lowered = str(line or '').lower()
        if any(token in lowered for token in _SUBTOTAL_TOKENS):
            subtotal_index = index
            break
    if subtotal_index is None:
        return []
    total_index: int | None = None
    for index in range(subtotal_index + 1, len(text_lines)):
        lowered = str(text_lines[index] or '').lower()
        if any(token in lowered for token in _TOTAL_TOKENS):
            total_index = index
            break
    if total_index is None or total_index <= subtotal_index:
        return []
    return text_lines[subtotal_index + 1:total_index]


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
