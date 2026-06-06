"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from app.receipt_ingestion.amounts import (
    amount_to_float as _amount_to_float,
    parse_decimal as _parse_decimal,
)


def _strip_accents(value: str | None) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFKD', str(value or '')) if not unicodedata.combining(ch))


def _normalize_discount_match_text(value: str | None) -> str:
    normalized = _strip_accents(value).lower()
    normalized = re.sub(r'(?i)\b(bonus|bbox|actie|korting|prijsvoordeel|uw voordeel|lidl plus|plus korting|deal)\b', ' ', normalized)
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def _extract_discount_entries(lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    amount_pattern = re.compile(r'(-?\d{1,6}(?:[\.,]\d{2}))')
    for index, raw_line in enumerate(lines):
        normalized = re.sub(r'\s+', ' ', str(raw_line or '')).strip()
        if len(normalized) < 2:
            continue
        lowered = normalized.lower()
        discount_signal = lowered.startswith(('bonus ', 'bbox ', 'korting ', 'actie ')) or any(token in lowered for token in (' korting', 'uw voordeel', 'prijsvoordeel', 'lidl plus', 'plus geeft meer voordeel'))
        if not discount_signal:
            continue
        if any(marker in lowered for marker in ('uw voordeel', 'totaal prijsvoordeel', 'totaal korting', 'bonus box premium')):
            continue
        matches = amount_pattern.findall(normalized)
        if not matches:
            continue
        amount = _parse_decimal(matches[-1])
        if amount is None:
            continue
        if amount > 0:
            amount = -amount
        if amount >= 0:
            continue
        label = amount_pattern.sub('', normalized).strip(' -')
        normalized_label = _normalize_discount_match_text(label or normalized)
        entries.append({
            'raw_label': label or normalized,
            'normalized_label': normalized_label,
            'amount': amount.quantize(Decimal('0.01')),
            'source_index': index,
            'is_generic_discount': normalized_label == '',
        })
    return entries


def _discount_match_score(discount_label: str | None, line_label: str | None) -> int:
    discount_normalized = _normalize_discount_match_text(discount_label)
    line_normalized = _normalize_discount_match_text(line_label)
    if not discount_normalized or not line_normalized:
        return 0
    discount_compact = discount_normalized.replace(' ', '')
    line_compact = line_normalized.replace(' ', '')
    score = 0
    if len(line_compact) >= 4 and line_compact in discount_compact:
        score += 100 + len(line_compact)
    if len(discount_compact) >= 4 and discount_compact in line_compact:
        score += 70 + len(discount_compact)
    line_tokens = [token for token in line_normalized.split() if len(token) >= 3]
    discount_tokens = [token for token in discount_normalized.split() if len(token) >= 3]
    for token in line_tokens:
        if token in discount_tokens:
            score += 30 + len(token)
        elif token in discount_compact:
            score += 18 + len(token)
    if line_tokens and discount_tokens and line_tokens[0] == discount_tokens[0]:
        score += 26 + len(line_tokens[0])
    common_prefix = 0
    for left, right in zip(discount_compact, line_compact):
        if left != right:
            break
        common_prefix += 1
    if common_prefix >= 4:
        score += 12 + common_prefix
    ratio = SequenceMatcher(None, discount_compact, line_compact).ratio()
    score += int(round(ratio * 20))
    return score


def _apply_discount_entries(lines: list[dict[str, Any]], discount_entries: list[dict[str, Any]]) -> Decimal | None:
    if not lines or not discount_entries:
        return None if not discount_entries else sum((entry['amount'] for entry in discount_entries), Decimal('0.00')).quantize(Decimal('0.01'))

    def attach_discount(target_index: int, amount: Decimal) -> None:
        current = _parse_decimal(str(lines[target_index].get('discount_amount'))) or Decimal('0.00')
        lines[target_index]['discount_amount'] = _amount_to_float((current + amount).quantize(Decimal('0.01')))

    def find_nearest_preceding_line_index(entry_source_index: int, *, max_distance: int | None = None) -> int | None:
        fallback_index = None
        fallback_source_index = -1
        for index, line in enumerate(lines):
            line_source_index = line.get('source_index')
            if line_source_index is None:
                continue
            if line_source_index > entry_source_index:
                continue
            if max_distance is not None and (entry_source_index - line_source_index) > max_distance:
                continue
            if line_source_index >= fallback_source_index:
                fallback_index = index
                fallback_source_index = line_source_index
        return fallback_index

    total_discount = Decimal('0.00')
    for entry in discount_entries:
        amount = entry['amount']
        total_discount += amount
        best_index = None
        best_score = 0
        second_best = 0
        for index, line in enumerate(lines):
            score = _discount_match_score(entry.get('normalized_label') or entry.get('raw_label'), line.get('normalized_label') or line.get('raw_label'))
            if score > best_score:
                second_best = best_score
                best_score = score
                best_index = index
            elif score > second_best:
                second_best = score

        if best_index is not None and best_score >= 20 and best_score != second_best:
            attach_discount(best_index, amount)
            continue

        entry_source_index = entry.get('source_index')
        if entry_source_index is None:
            continue

        if entry.get('is_generic_discount'):
            nearby_index = find_nearest_preceding_line_index(int(entry_source_index), max_distance=2)
            if nearby_index is not None:
                attach_discount(nearby_index, amount)
            continue

        fallback_index = find_nearest_preceding_line_index(int(entry_source_index))
        if fallback_index is not None:
            attach_discount(fallback_index, amount)
    return total_discount.quantize(Decimal('0.01')) if total_discount != Decimal('0.00') else None


def _is_validated_savings_action_line(line: dict[str, Any]) -> bool:
    """Return True for value lines already validated by the savings/action parser.

    This is intentionally narrow. It does not make generic loyalty text a product:
    only lines produced by _extract_savings_action_lines with append_branch
    savings_action_line are allowed to pass the final non-product label filter.
    """
    if not isinstance(line, dict):
        return False
    producer_trace = line.get('producer_trace') or {}
    if not isinstance(producer_trace, dict):
        return False
    return (
        producer_trace.get('function_name') == '_extract_savings_action_lines'
        and producer_trace.get('append_branch') == 'savings_action_line'
    )
