"""PLUS article-block recovery diagnostics.

Diagnose-only module for PLUS image receipts.

Purpose:
- inspect Paddle/raw OCR lines inside the PLUS article block;
- compare those lines with currently parsed receipt lines;
- report product-like OCR lines that were not converted into parser lines;
- do not alter parser output.

No hardcoded article names, receipt IDs, filenames or receipt-specific prices.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


_MONEY_RE = re.compile(r'(?<![A-Za-z0-9])[-€£CEe]?\s*\d{1,5}(?:[.,]\d{2})(?![A-Za-z0-9])')
_LETTER_RE = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]')

_ARTICLE_HEADER_RE = re.compile(
    r'(?:omschrijving|onschrijving|dnschrijving|beschrijving).*(?:bedrag|p\.?\s*st|st/kg|p\s*st/kg)',
    re.IGNORECASE,
)

_ARTICLE_BLOCK_END_RE = re.compile(
    r'\b(?:subtotaal|subtotal|klantticket|terminal|merchant|transactie|autorisatie|betaling|contactless|contactiess|tontactless|leesmethode|wisselgeld|btw|kaart|pin)\b',
    re.IGNORECASE,
)

_NON_ARTICLE_RE = re.compile(
    r'\b(?:subtotaal|subtotal|totaal|totael|yotaal|lotaal|pluspunten|digitale\s+zegels|zegel|actie|korting|klantticket|terminal|merchant|transactie|betaling|contactless|contactiess|tontactless|leesmethode|wisselgeld|btw|kaart|pin|poi)\b',
    re.IGNORECASE,
)


def _money(value: Any) -> Decimal:
    if value is None or value == '':
        return Decimal('0.00')
    try:
        return Decimal(str(value).replace(',', '.')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return Decimal('0.00')


def _parse_money_token(token: str) -> Decimal | None:
    cleaned = str(token or '').strip()
    cleaned = cleaned.replace('€', '').replace('£', '')
    cleaned = re.sub(r'^[CEe]\s*', '', cleaned)
    cleaned = cleaned.replace(' ', '').replace(',', '.')
    try:
        return Decimal(cleaned).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def _amount_tokens(line: str) -> list[Decimal]:
    values: list[Decimal] = []
    for match in _MONEY_RE.finditer(str(line or '')):
        value = _parse_money_token(match.group(0))
        if value is not None:
            values.append(value)
    return values


def _normalize_text(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip().lower()


def _source_indexes(lines: list[dict[str, Any]] | None) -> set[int]:
    indexes: set[int] = set()
    for line in lines or []:
        trace = line.get('producer_trace') if isinstance(line, dict) else None
        if not isinstance(trace, dict):
            continue
        try:
            indexes.add(int(trace.get('source_index')))
        except Exception:
            continue
    return indexes


def _article_block_bounds(text_lines: list[str] | None) -> tuple[int, int]:
    lines = list(text_lines or [])
    start = 0

    for idx, raw in enumerate(lines):
        if _ARTICLE_HEADER_RE.search(str(raw or '')):
            start = idx + 1
            break

    end = len(lines)
    for idx in range(start, len(lines)):
        raw = str(lines[idx] or '')
        if _ARTICLE_BLOCK_END_RE.search(raw):
            end = idx
            break

    return start, end


def _is_product_like_article_block_line(raw: str) -> bool:
    value = str(raw or '').strip()
    normalized = _normalize_text(value)

    if not value:
        return False
    if not _LETTER_RE.search(value):
        return False
    if _NON_ARTICLE_RE.search(normalized):
        return False

    amounts = _amount_tokens(value)
    if not amounts:
        return False

    # Product-like lines should have text before the final amount.
    last_amount_match = list(_MONEY_RE.finditer(value))[-1]
    prefix = value[:last_amount_match.start()]
    if not _LETTER_RE.search(prefix):
        return False

    return True


def diagnose_plus_article_block_recovery(
    *,
    text_lines: list[str] | None,
    current_lines: list[dict[str, Any]] | None,
    total_amount: Any = None,
    discount_total: Any = None,
) -> dict[str, Any]:
    """Return PLUS raw-OCR article-block diagnostics without changing output."""

    lines = list(text_lines or [])
    start, end = _article_block_bounds(lines)
    parsed_source_indexes = _source_indexes(current_lines)

    current_line_sum = sum((_money(line.get('line_total')) for line in (current_lines or [])), Decimal('0.00'))
    current_line_discount_sum = sum((_money(line.get('discount_amount')) for line in (current_lines or [])), Decimal('0.00'))
    current_discount_total = _money(discount_total)
    current_total = _money(total_amount) if total_amount is not None else None
    current_net = (current_line_sum + current_line_discount_sum + current_discount_total).quantize(Decimal('0.01'))

    if current_total is None:
        current_diff = None
    else:
        current_diff = (current_net - current_total).quantize(Decimal('0.01'))

    candidates: list[dict[str, Any]] = []
    article_block_lines: list[dict[str, Any]] = []

    for idx in range(start, end):
        raw = str(lines[idx] or '')
        amounts = _amount_tokens(raw)
        product_like = _is_product_like_article_block_line(raw)
        already_parsed = idx in parsed_source_indexes

        item = {
            'source_index': idx,
            'raw_line': raw,
            'amounts': [float(value) for value in amounts],
            'last_amount': float(amounts[-1]) if amounts else None,
            'product_like': product_like,
            'already_parsed': already_parsed,
        }
        article_block_lines.append(item)

        if not product_like or already_parsed or not amounts:
            continue

        last_amount = amounts[-1]
        net_if_added = (current_net + last_amount).quantize(Decimal('0.01'))
        diff_if_added = None if current_total is None else (net_if_added - current_total).quantize(Decimal('0.01'))

        candidates.append({
            'source_index': idx,
            'raw_line': raw,
            'candidate_line_total': float(last_amount),
            'amounts': [float(value) for value in amounts],
            'current_diff': float(current_diff) if current_diff is not None else None,
            'diff_if_added_last_amount': float(diff_if_added) if diff_if_added is not None else None,
            'reason': 'unparsed_product_like_line_in_plus_article_block',
        })

    return {
        'scope': 'PLUS profile image receipts only',
        'mode': 'diagnose_only',
        'article_block_start_index': start,
        'article_block_end_index': end,
        'article_block_line_count': max(0, end - start),
        'current_line_count': len(current_lines or []),
        'current_line_sum': float(current_line_sum),
        'current_line_discount_sum': float(current_line_discount_sum),
        'current_discount_total': float(current_discount_total),
        'current_net': float(current_net),
        'current_total': float(current_total) if current_total is not None else None,
        'current_diff': float(current_diff) if current_diff is not None else None,
        'article_block_lines': article_block_lines,
        'unparsed_product_like_candidates': candidates,
        'candidate_count': len(candidates),
    }


__all__ = ['diagnose_plus_article_block_recovery']
