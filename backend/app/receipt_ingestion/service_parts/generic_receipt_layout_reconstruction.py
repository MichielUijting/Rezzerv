"""Generic OCR layout reconstruction for image receipts.

Uses OCR geometry and amount patterns only. Do not add article names,
receipt identifiers, hashes, addresses or fixed receipt totals here.
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
AMOUNT_RE = re.compile(r'^[€CE]?-?\d{1,6}(?:[\.,]\d{2})(?:\s*EUR)?$', re.I)
AMOUNT_TOKEN_RE = re.compile(r'[€CE]?-?\d{1,6}(?:[\.,]\d{2})(?:\s*EUR)?', re.I)
WORD_RE = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]{3,}')
STOP_TOKENS = ('subtotaal', 'totaal', 'betaald', 'terminal', 'betaling', 'btw ', 'over eur')
PAY_TOKENS = ('contactless', 'terminal', 'merchant', 'betaling', 'kaart:', 'maestro', 'pin', 'wisselgeld', 'betaald')
HEADER_TOKENS = ('omschrijving', 'onschrijving', 'p st/kg', 'bedrag', 'prijs', 'aantal')
START_TOKENS = ('omschrijving', 'onschrijving', 'artikel', 'prijs', 'bedrag')


def norm(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def amount_value(value: Any) -> Decimal | None:
    raw = norm(value).upper().replace('€', '').replace('EUR', '').strip()
    if raw.startswith(('C', 'E')):
        raw = raw[1:]
    try:
        return Decimal(raw.replace(',', '.')).quantize(Decimal('0.01'))
    except Exception:
        return None


def is_amount(value: Any) -> bool:
    return bool(AMOUNT_RE.fullmatch(norm(value)))


def last_amount(value: Any) -> Decimal | None:
    matches = AMOUNT_TOKEN_RE.findall(norm(value))
    return amount_value(matches[-1]) if matches else None


def anchor(box: Any) -> dict[str, float] | None:
    try:
        if isinstance(box, (list, tuple)) and len(box) == 4 and not isinstance(box[0], (list, tuple)):
            x1, y1, x2, y2 = [float(v) for v in box]
            return {'cy': (y1 + y2) / 2, 'h': max(1.0, abs(y2 - y1)), 'x1': min(x1, x2), 'x2': max(x1, x2)}
        points = [(float(p[0]), float(p[1])) for p in (box or []) if isinstance(p, (list, tuple)) and len(p) >= 2]
        if not points:
            return None
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return {'cy': (min(ys) + max(ys)) / 2, 'h': max(1.0, max(ys) - min(ys)), 'x1': min(xs), 'x2': max(xs)}
    except Exception:
        return None


def fragments(texts: list[str], boxes: list[Any]) -> list[dict[str, Any]]:
    result = []
    for index, (text, box) in enumerate(zip(texts, boxes)):
        a = anchor(box)
        if a and norm(text):
            result.append({'i': index, 'text': norm(text), **a})
    return result


def sort_key(item: dict[str, Any]) -> tuple[float, float, int]:
    return (float(item.get('cy') or 0), float(item.get('x1') or 0), int(item.get('i') or 0))


def is_label(item: dict[str, Any]) -> bool:
    text = norm(item.get('text'))
    low = text.lower()
    return bool(text and not is_amount(text) and WORD_RE.search(text) and not any(t in low for t in PAY_TOKENS + HEADER_TOKENS + STOP_TOKENS))


def has_suspicious_merges(lines: list[str]) -> bool:
    for line in lines or []:
        low = line.lower()
        if any(t in low for t in STOP_TOKENS):
            continue
        if len(AMOUNT_TOKEN_RE.findall(line)) >= 2 and len(WORD_RE.findall(line)) >= 3:
            return True
    return False


def article_block(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(items, key=sort_key)
    start = None
    for item in ordered:
        if any(t in norm(item.get('text')).lower() for t in START_TOKENS):
            start = float(item.get('cy') or 0)
            break
    if start is None:
        for item in ordered:
            if is_label(item) and float(item.get('cy') or 0) > 120:
                start = float(item.get('cy') or 0) - max(20.0, float(item.get('h') or 0) * 1.5)
                break
    if start is None:
        return []
    stop = None
    for item in ordered:
        y = float(item.get('cy') or 0)
        if y > start and any(t in norm(item.get('text')).lower() for t in STOP_TOKENS):
            stop = y
            break
    if stop is None:
        return []
    return [item for item in ordered if start < float(item.get('cy') or 0) < stop]


def direct_line(item: dict[str, Any]) -> str | None:
    text = norm(item.get('text'))
    amounts = AMOUNT_TOKEN_RE.findall(text)
    if not is_label(item) or not amounts:
        return None
    if len(amounts) == 1 or re.search(r'\b\d{1,4}\s*[xX]\s*\d{1,6}[\.,]\d{2}\s+\d{1,6}[\.,]\d{2}\b', text):
        return text
    return None


def assign_line(label: dict[str, Any], amounts: list[dict[str, Any]], height: float) -> str | None:
    direct = direct_line(label)
    if direct:
        return direct
    y = float(label.get('cy') or 0)
    right = float(label.get('x2') or 0)
    candidates = []
    for amount in amounts:
        dy = abs(float(amount.get('cy') or 0) - y)
        left = float(amount.get('x1') or 0)
        if dy <= max(14.0, height * 0.8) and left + height >= right:
            candidates.append((dy, max(0.0, left - right), amount))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], row[1]))
    amount_text = norm(candidates[0][2].get('text'))
    return norm(f"{norm(label.get('text'))} {amount_text}") if amount_value(amount_text) is not None else None


def candidate_lines(block: list[dict[str, Any]]) -> list[str]:
    heights = [float(item.get('h') or 0) for item in block if item.get('h')]
    h = median(heights) if heights else 24.0
    amount_items = [item for item in block if is_amount(item.get('text'))]
    result = []
    seen = set()
    for label in sorted([item for item in block if is_label(item)], key=sort_key):
        line = assign_line(label, amount_items, h)
        if not line or last_amount(line) is None:
            continue
        key = re.sub(r'\W+', '', line.lower())
        if key not in seen:
            seen.add(key)
            result.append(line)
    return result


def line_sum(lines: list[str]) -> Decimal:
    total = Decimal('0.00')
    for line in lines:
        value = last_amount(line)
        if value is not None:
            total += value
    return total.quantize(Decimal('0.01'))


def totals(lines: list[str]) -> list[Decimal]:
    found = []
    for line in lines or []:
        low = line.lower()
        if 'totaal' in low or 'betaald' in low:
            value = last_amount(line)
            if value and value > 0:
                found.append(value)
    return found


def replace_block(current_lines: list[str], reconstructed: list[str]) -> list[str] | None:
    start = None
    for idx, line in enumerate(current_lines):
        if any(t in line.lower() for t in START_TOKENS):
            start = idx + 1
            break
    if start is None:
        for idx, line in enumerate(current_lines):
            if WORD_RE.search(line) and AMOUNT_TOKEN_RE.search(line):
                start = idx
                break
    if start is None:
        return None
    stop = None
    for idx in range(start, len(current_lines)):
        if any(t in current_lines[idx].lower() for t in STOP_TOKENS):
            stop = idx
            break
    if stop is None or stop <= start:
        return None
    return current_lines[:start] + reconstructed + current_lines[stop:]


def apply_generic_receipt_layout_reconstruction(*, filename: str, texts: list[str], boxes: list[Any], current_lines: list[str]) -> list[str] | None:
    suffix = Path(filename or '').suffix.lower()
    if suffix not in IMAGE_EXTENSIONS or not texts or not boxes or len(texts) != len(boxes):
        return None
    if not has_suspicious_merges(current_lines):
        return None
    block = article_block(fragments(texts, boxes))
    if len(block) < 8:
        return None
    reconstructed = candidate_lines(block)
    if len(reconstructed) < 8:
        return None
    current_totals = totals(current_lines)
    if current_totals and not any(abs(total - line_sum(reconstructed)) <= Decimal('0.02') for total in current_totals):
        return None
    return replace_block(current_lines, reconstructed)
