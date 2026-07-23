"""PLUS non-article financial correction diagnostics.

Diagnose-only module.

Purpose:
- financially validate PLUS bbox reconstructed article rows;
- include non-article financial corrections:
  - statiegeld in the article block;
  - PLUSpunten / digital points;
  - zegel / spaaraction lines;
  - action discounts between Subtotaal and Totaal;
- keep "DE TOTALE KORTING IS" as control-only;
- do not alter parser output or database state.

No hardcoded article names, receipt IDs, filenames or receipt-specific prices.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.receipt_ingestion.parsing.plus_bbox_line_reconstruction import (
    diagnose_plus_bbox_article_reconstruction,
)


_MONEY_RE = re.compile(r'[-€£CEe]?\s*\d{1,6}(?:[.,]\s?\d{2})')
_SUBTOTAL_RE = re.compile(r'\bsubtotaal\b', re.IGNORECASE)
_TOTAL_RE = re.compile(r'\b(?:totaal|totael|yotaal|lotaal)\b', re.IGNORECASE)
_TOTAL_DISCOUNT_RE = re.compile(r'\b(?:totale\s+korting|de\s+totale\s+korting)\b', re.IGNORECASE)
_DISCOUNT_RE = re.compile(r'\b(?:actie|aktie|korting|voordeel)\b', re.IGNORECASE)
_PLUSPOINTS_RE = re.compile(r'\b(?:pluspunten|pluspunten digitaal|piuspunten)\b', re.IGNORECASE)
_STAMPS_RE = re.compile(r'\b(?:zegel|zegels|mepal|buitenservies|buitensservies|buitens ervies)\b', re.IGNORECASE)
_STATIEGELD_RE = re.compile(r'\bstatiegeld\b', re.IGNORECASE)
_NON_ARTICLE_FINANCIAL_RE = re.compile(
    r'\b(?:statiegeld|pluspunten|piuspunten|digitale\s+zegels|zegel|zegels|mepal|buitenservies|buitensservies|buitens ervies)\b',
    re.IGNORECASE,
)
_PAYMENT_OR_FOOTER_RE = re.compile(
    r'\b(?:klantticket|terminal|merchant|transactie|autorisatie|betaling|contactless|contactiess|leesmethode|wisselgeld|btw|kaart|pin|poi|par:|openingstijden|prettige|bonnr|www\.)\b',
    re.IGNORECASE,
)


def _normalize(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _to_decimal(value: Any) -> Decimal:
    cleaned = str(value or '').strip()
    cleaned = cleaned.replace('€', '').replace('£', '')
    cleaned = re.sub(r'^[CEe]\s*', '', cleaned)
    cleaned = re.sub(r'\s+', '', cleaned)
    cleaned = cleaned.replace(',', '.')
    try:
        return Decimal(cleaned).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return Decimal('0.00')


def _amount_tokens(raw: str) -> list[Decimal]:
    return [_to_decimal(match.group(0)) for match in _MONEY_RE.finditer(str(raw or ''))]


def _signed_amounts_from_line(raw: str) -> list[Decimal]:
    text = _normalize(raw)
    lowered = text.lower()
    signed: list[Decimal] = []

    for match in _MONEY_RE.finditer(text):
        token = match.group(0)
        amount = _to_decimal(token)
        prefix = text[max(0, match.start() - 5):match.start()]

        if '-' in token or '-' in prefix:
            amount = -abs(amount)
        elif _DISCOUNT_RE.search(lowered):
            amount = -abs(amount)

        signed.append(amount.quantize(Decimal('0.01')))

    return signed


def _find_subtotal_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if _SUBTOTAL_RE.search(line or ''):
            return index
    return None


def _find_footer_index(lines: list[str], start_index: int | None) -> int:
    start = 0 if start_index is None else start_index + 1
    for index in range(start, len(lines)):
        if _PAYMENT_OR_FOOTER_RE.search(lines[index] or ''):
            return index
    return len(lines)


def _extract_subtotal(lines: list[str], subtotal_index: int | None) -> Decimal | None:
    if subtotal_index is None or subtotal_index >= len(lines):
        return None

    amounts = _amount_tokens(lines[subtotal_index])
    return amounts[-1] if amounts else None


def _find_total_candidates(lines: list[str], subtotal_index: int | None) -> list[dict[str, Any]]:
    if subtotal_index is None:
        return []

    footer_index = _find_footer_index(lines, subtotal_index)
    candidates: list[dict[str, Any]] = []

    for index in range(subtotal_index + 1, footer_index):
        raw = lines[index] or ''
        text = _normalize(raw)
        if not text:
            continue
        if _TOTAL_DISCOUNT_RE.search(text):
            continue

        amounts = _amount_tokens(text)
        if not amounts:
            continue

        if _TOTAL_RE.search(text):
            candidates.append({
                'source_index': index,
                'raw_line': text,
                'amount': amounts[-1],
                'reason': 'explicit_total_label',
            })
            continue

        if len(amounts) == 1 and not _DISCOUNT_RE.search(text) and not _NON_ARTICLE_FINANCIAL_RE.search(text):
            # PLUS photo OCR can return the total as a bare amount line, e.g. "E45,14".
            if re.fullmatch(r'[€£CEe]?\s*\d{1,6}(?:[.,]\s?\d{2})', text):
                candidates.append({
                    'source_index': index,
                    'raw_line': text,
                    'amount': amounts[-1],
                    'reason': 'bare_amount_total_candidate',
                })

    return candidates


def _choose_total_amount(
    candidates: list[dict[str, Any]],
    expected_net: Decimal | None,
) -> tuple[Decimal | None, dict[str, Any] | None]:
    if not candidates:
        return None, None

    explicit = [candidate for candidate in candidates if candidate.get('reason') == 'explicit_total_label']
    pool = explicit if explicit else candidates

    if expected_net is None:
        chosen = pool[0]
        return chosen['amount'], chosen

    chosen = min(pool, key=lambda candidate: abs(candidate['amount'] - expected_net))
    return chosen['amount'], chosen


def _runtime_article_block(lines: list[str]) -> list[tuple[int, str]]:
    start = None
    end = None

    for index, line in enumerate(lines):
        low = (line or '').lower()
        if ('omschrijving' in low or 'onschrijving' in low or 'dnschrijving' in low) and 'bedrag' in low:
            start = index + 1
            break

    if start is None:
        return []

    for index in range(start, len(lines)):
        if _SUBTOTAL_RE.search(lines[index] or ''):
            end = index
            break

    if end is None:
        end = len(lines)

    return [(index, lines[index]) for index in range(start, end)]


def _collect_extra_statiegeld_from_runtime(
    runtime_lines: list[str],
    already_used_amounts: list[Decimal],
) -> tuple[list[dict[str, Any]], Decimal]:
    rows: list[dict[str, Any]] = []
    total = Decimal('0.00')
    remaining_used = list(already_used_amounts)

    for source_index, raw in _runtime_article_block(runtime_lines):
        text = _normalize(raw)
        if not _STATIEGELD_RE.search(text):
            continue

        # Only standalone statiegeld lines are added here.
        # Mixed article+statiegeld rows are handled by bbox rows if they were paired.
        if not text.lower().startswith('statiegeld'):
            continue

        amounts = _amount_tokens(text)
        if not amounts:
            continue

        amount = amounts[-1]

        # Avoid double counting values that bbox already used as non-article financial.
        matched_existing = False
        for idx, used in enumerate(remaining_used):
            if used == amount:
                matched_existing = True
                remaining_used.pop(idx)
                break

        if matched_existing:
            continue

        rows.append({
            'source_index': source_index,
            'classification': 'runtime_article_block_statiegeld',
            'raw_line': text,
            'amount': float(amount),
            'used_in_financial_total': True,
        })
        total += amount

    return rows, total.quantize(Decimal('0.01'))


def _collect_discount_block(
    lines: list[str],
    subtotal_index: int | None,
) -> tuple[list[dict[str, Any]], Decimal, Decimal | None]:
    if subtotal_index is None:
        return [], Decimal('0.00'), None

    footer_index = _find_footer_index(lines, subtotal_index)
    rows: list[dict[str, Any]] = []
    discount_total = Decimal('0.00')
    total_discount_control: Decimal | None = None

    for index in range(subtotal_index + 1, footer_index):
        raw = lines[index] or ''
        text = _normalize(raw)

        if not text:
            continue

        signed_amounts = _signed_amounts_from_line(text)
        plain_amounts = _amount_tokens(text)

        if not plain_amounts:
            continue

        if _TOTAL_DISCOUNT_RE.search(text):
            total_discount_control = abs(signed_amounts[-1]) if signed_amounts else abs(plain_amounts[-1])
            rows.append({
                'source_index': index,
                'classification': 'total_discount_control_only',
                'raw_line': text,
                'amounts': [float(amount) for amount in signed_amounts],
                'line_total': 0.0,
                'used_in_total': False,
            })
            continue

        if _PLUSPOINTS_RE.search(text):
            # Generic PLUS interpretation:
            # - one amount on PLUSpunten line => positive financial correction;
            # - multiple amounts => first is promo/action value, last is points/stamps correction.
            if len(plain_amounts) == 1:
                line_total = abs(plain_amounts[-1])
                used_amounts = [line_total]
            else:
                discount_part = -abs(plain_amounts[0])
                correction_part = abs(plain_amounts[-1])
                line_total = (discount_part + correction_part).quantize(Decimal('0.01'))
                used_amounts = [discount_part, correction_part]

            discount_total += line_total
            rows.append({
                'source_index': index,
                'classification': 'pluspoints_financial_correction',
                'raw_line': text,
                'amounts': [float(amount) for amount in used_amounts],
                'line_total': float(line_total),
                'used_in_total': True,
            })
            continue

        if _DISCOUNT_RE.search(text):
            used_amounts = [amount for amount in signed_amounts if amount < Decimal('0.00')]
            if not used_amounts:
                used_amounts = [-abs(plain_amounts[-1])]

            line_total = sum(used_amounts, Decimal('0.00')).quantize(Decimal('0.01'))
            discount_total += line_total

            rows.append({
                'source_index': index,
                'classification': 'discount',
                'raw_line': text,
                'amounts': [float(amount) for amount in used_amounts],
                'line_total': float(line_total),
                'used_in_total': True,
            })
            continue

        if _STAMPS_RE.search(text) or _NON_ARTICLE_FINANCIAL_RE.search(text):
            negative_amounts = [amount for amount in signed_amounts if amount < Decimal('0.00')]
            positive_amounts = [abs(amount) for amount in signed_amounts if amount > Decimal('0.00')]

            if negative_amounts:
                used_amounts = negative_amounts
            elif positive_amounts and len(positive_amounts) == 1:
                used_amounts = positive_amounts
            else:
                used_amounts = []

            line_total = sum(used_amounts, Decimal('0.00')).quantize(Decimal('0.01'))
            if line_total != Decimal('0.00'):
                discount_total += line_total

            rows.append({
                'source_index': index,
                'classification': 'non_article_financial_correction',
                'raw_line': text,
                'amounts': [float(amount) for amount in used_amounts],
                'line_total': float(line_total),
                'used_in_total': line_total != Decimal('0.00'),
            })

    return rows, discount_total.quantize(Decimal('0.01')), total_discount_control


def _row_amount(row: dict[str, Any]) -> Decimal:
    return _to_decimal(row.get('amount'))


def diagnose_plus_non_article_financial_corrections(
    texts: list[Any],
    boxes: list[Any],
    runtime_lines: list[str],
) -> dict[str, Any]:
    bbox_diag = diagnose_plus_bbox_article_reconstruction(texts, boxes)

    article_rows: list[dict[str, Any]] = []
    non_article_rows: list[dict[str, Any]] = []

    for row in bbox_diag.get('rows') or []:
        amount = _row_amount(row)
        normalized = dict(row)
        normalized['amount_decimal'] = amount

        if row.get('classification') == 'non_article_financial':
            non_article_rows.append(normalized)
        else:
            article_rows.append(normalized)

    article_total = sum((row['amount_decimal'] for row in article_rows), Decimal('0.00')).quantize(Decimal('0.01'))
    bbox_non_article_total = sum((row['amount_decimal'] for row in non_article_rows), Decimal('0.00')).quantize(Decimal('0.01'))

    extra_statiegeld_rows, extra_statiegeld_total = _collect_extra_statiegeld_from_runtime(
        runtime_lines=runtime_lines,
        already_used_amounts=[row['amount_decimal'] for row in non_article_rows],
    )

    non_article_financial_total = (bbox_non_article_total + extra_statiegeld_total).quantize(Decimal('0.01'))

    lines = list(runtime_lines or [])
    subtotal_index = _find_subtotal_index(lines)
    subtotal_amount = _extract_subtotal(lines, subtotal_index)

    discount_rows, discount_total, total_discount_control = _collect_discount_block(lines, subtotal_index)

    pre_discount_total = (article_total + non_article_financial_total).quantize(Decimal('0.01'))
    net_total = (pre_discount_total + discount_total).quantize(Decimal('0.01'))

    total_candidates = _find_total_candidates(lines, subtotal_index)
    total_amount, chosen_total = _choose_total_amount(total_candidates, net_total)

    diff_to_subtotal = None
    if subtotal_amount is not None:
        diff_to_subtotal = (pre_discount_total - subtotal_amount).quantize(Decimal('0.01'))

    diff_to_total = None
    if total_amount is not None:
        diff_to_total = (net_total - total_amount).quantize(Decimal('0.01'))

    return {
        'mode': 'diagnose_only',
        'version': 'PLUS-01I',
        'bbox_version': bbox_diag.get('version'),
        'bounds': bbox_diag.get('bounds'),
        'article_rows': [
            {k: v for k, v in row.items() if k != 'amount_decimal'}
            for row in article_rows
        ],
        'bbox_non_article_financial_rows': [
            {k: v for k, v in row.items() if k != 'amount_decimal'}
            for row in non_article_rows
        ],
        'extra_runtime_non_article_financial_rows': extra_statiegeld_rows,
        'discount_rows': discount_rows,
        'article_total': float(article_total),
        'bbox_non_article_financial_total': float(bbox_non_article_total),
        'extra_runtime_non_article_financial_total': float(extra_statiegeld_total),
        'non_article_financial_total': float(non_article_financial_total),
        'pre_discount_total': float(pre_discount_total),
        'discount_total': float(discount_total),
        'net_total': float(net_total),
        'subtotal_amount': float(subtotal_amount) if subtotal_amount is not None else None,
        'total_amount': float(total_amount) if total_amount is not None else None,
        'chosen_total_candidate': {
            **chosen_total,
            'amount': float(chosen_total['amount']),
        } if chosen_total is not None else None,
        'total_candidates': [
            {
                **candidate,
                'amount': float(candidate['amount']),
            }
            for candidate in total_candidates
        ],
        'total_discount_control': float(total_discount_control) if total_discount_control is not None else None,
        'diff_to_subtotal': float(diff_to_subtotal) if diff_to_subtotal is not None else None,
        'diff_to_total': float(diff_to_total) if diff_to_total is not None else None,
        'exact_subtotal_match': diff_to_subtotal == Decimal('0.00') if diff_to_subtotal is not None else False,
        'exact_total_match': diff_to_total == Decimal('0.00') if diff_to_total is not None else False,
        'unused_text_fragments': bbox_diag.get('unused_text_fragments') or [],
        'unused_unit_fragments': bbox_diag.get('unused_unit_fragments') or [],
    }


__all__ = ['diagnose_plus_non_article_financial_corrections']
