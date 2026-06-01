from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
_AMOUNT_RE = re.compile(r'^[€CE]?-?\d{1,6}(?:[\.,]\d{2})(?:\s*EUR)?$', re.IGNORECASE)
_AMOUNT_TOKEN_RE = re.compile(r'[€CE]?-?\d{1,6}(?:[\.,]\d{2})(?:\s*EUR)?', re.IGNORECASE)
_ARTICLE_HINT_RE = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]{3,}')
_START_TOKENS = ('omschrijving', 'onschrijving')
_STOP_TOKENS = ('subtotaal', 'totaal', 'klantticket', 'terminal', 'betaling', 'btw groep', 'btw laag')
_DISCOUNT_TOKENS = ('plus geeft', 'korting', 'actie', 'voordeel')
_HEADER_TOKENS = ('omschrijving', 'onschrijving', 'p st/kg', 'bedrag')
_PLUS_PROFILE_TOKENS = ('plus', 'pluspunten')


def _norm(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _is_amount(text: Any) -> bool:
    return bool(_AMOUNT_RE.fullmatch(_norm(text)))


def _amount_value(text: Any) -> float | None:
    raw = _norm(text).upper().replace('€', '').replace('EUR', '').strip()
    if raw.startswith('C') or raw.startswith('E'):
        raw = raw[1:]
    raw = raw.replace(',', '.')
    try:
        return float(Decimal(raw))
    except Exception:
        return None


def _ocr_bbox_to_anchor(bbox: Any) -> dict[str, float] | None:
    try:
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and not isinstance(bbox[0], (list, tuple)):
            x1, y1, x2, y2 = [float(value) for value in bbox]
            return {
                'center_y': (y1 + y2) / 2.0,
                'height': max(1.0, y2 - y1),
                'min_x': min(x1, x2),
                'max_x': max(x1, x2),
                'min_y': min(y1, y2),
                'max_y': max(y1, y2),
            }
        points: list[tuple[float, float]] = []
        for point in bbox or []:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append((float(point[0]), float(point[1])))
        if not points:
            return None
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return {
            'center_y': (min(ys) + max(ys)) / 2.0,
            'height': max(1.0, max(ys) - min(ys)),
            'min_x': min(xs),
            'max_x': max(xs),
            'min_y': min(ys),
            'max_y': max(ys),
        }
    except Exception:
        return None


def _fragments_from_ocr(texts: list[str], boxes: list[Any]) -> list[dict[str, Any]]:
    fragments: list[dict[str, Any]] = []
    for index, (text, box) in enumerate(zip(texts, boxes)):
        normalized = _norm(text)
        if not normalized:
            continue
        anchor = _ocr_bbox_to_anchor(box)
        if anchor is None:
            continue
        fragments.append({
            'global_index': index,
            'text': normalized,
            **anchor,
        })
    return fragments


def _sort_key(fragment: dict[str, Any]) -> tuple[float, float, int]:
    return (float(fragment.get('center_y') or 0), float(fragment.get('min_x') or 0), int(fragment.get('global_index') or 0))


def _line_key(fragment: dict[str, Any]) -> str:
    return _norm(fragment.get('text')).lower()


def _is_text_label(fragment: dict[str, Any]) -> bool:
    text = _norm(fragment.get('text'))
    if not text or _is_amount(text):
        return False
    if not _ARTICLE_HINT_RE.search(text):
        return False
    if text.lower().startswith('2ee'):
        return False
    return True


def _looks_like_plus_receipt(texts: list[str]) -> bool:
    normalized = [_norm(text).lower() for text in texts if _norm(text)]
    if not any(text == 'plus' or text.startswith('plus ') for text in normalized[:20]):
        return False
    return any(any(token in text for token in _PLUS_PROFILE_TOKENS) for text in normalized)


def _has_suspicious_article_merges(lines: list[str]) -> bool:
    for line in lines:
        lowered = line.lower()
        if any(token in lowered for token in _STOP_TOKENS):
            continue
        amount_count = len(_AMOUNT_TOKEN_RE.findall(line))
        word_count = len(re.findall(r'[A-Za-zÀ-ÖØ-öø-ÿ]{3,}', line))
        if amount_count >= 2 and word_count >= 4:
            return True
    return False


def _detect_article_block(fragments: list[dict[str, Any]]) -> tuple[float, float, list[dict[str, Any]]]:
    ordered = sorted(fragments, key=_sort_key)
    start_y = None
    for item in ordered:
        text = _line_key(item)
        if any(token in text for token in _START_TOKENS):
            start_y = float(item.get('center_y') or 0)
            break
    if start_y is None:
        for item in ordered:
            if _is_text_label(item) and float(item.get('center_y') or 0) > 250:
                start_y = float(item.get('center_y') or 0) - 30
                break
    stop_y = None
    for item in ordered:
        y = float(item.get('center_y') or 0)
        if start_y is not None and y <= start_y:
            continue
        text = _line_key(item)
        if any(token in text for token in _STOP_TOKENS):
            stop_y = y
            break
    if start_y is None:
        return 0.0, 0.0, []
    if stop_y is None:
        return 0.0, 0.0, []
    block = [item for item in ordered if start_y < float(item.get('center_y') or 0) < stop_y]
    return start_y, stop_y, block


def _group_labels(block: list[dict[str, Any]], median_height: float) -> list[dict[str, Any]]:
    labels = [item for item in block if _is_text_label(item) and not any(token in _line_key(item) for token in _HEADER_TOKENS)]
    rows: list[dict[str, Any]] = []
    y_tolerance = max(4.0, median_height * 0.22)
    for fragment in sorted(labels, key=_sort_key):
        text = _norm(fragment.get('text'))
        y = float(fragment.get('center_y') or 0)
        best = None
        best_delta = None
        for row in rows:
            delta = abs(y - float(row['center_y']))
            if delta <= y_tolerance and (best_delta is None or delta < best_delta):
                best = row
                best_delta = delta
        if best is None:
            rows.append({
                'label': text,
                'label_fragments': [fragment],
                'center_y': y,
                'min_x': float(fragment.get('min_x') or 0),
                'max_x': float(fragment.get('max_x') or 0),
                'is_discount_context': any(token in text.lower() for token in _DISCOUNT_TOKENS),
                'amounts': [],
            })
        else:
            best['label_fragments'].append(fragment)
            ordered = sorted(best['label_fragments'], key=lambda item: float(item.get('min_x') or 0))
            best['label'] = _norm(' '.join(_norm(item.get('text')) for item in ordered))
            best['center_y'] = median(float(item.get('center_y') or 0) for item in ordered)
            best['min_x'] = min(float(item.get('min_x') or 0) for item in ordered)
            best['max_x'] = max(float(item.get('max_x') or 0) for item in ordered)
            best['is_discount_context'] = any(token in best['label'].lower() for token in _DISCOUNT_TOKENS)
    return sorted(rows, key=lambda row: float(row['center_y']))


def _amount_fragments(block: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in block if _is_amount(item.get('text'))]


def _previous_label_row(rows: list[dict[str, Any]], amount_y: float) -> dict[str, Any] | None:
    candidates = [row for row in rows if float(row['center_y']) <= amount_y]
    return candidates[-1] if candidates else None


def _nearest_discount_row(rows: list[dict[str, Any]], amount_y: float, max_delta: float) -> dict[str, Any] | None:
    best = None
    best_delta = None
    for row in rows:
        if not row.get('is_discount_context'):
            continue
        delta = abs(amount_y - float(row['center_y']))
        if delta <= max_delta and (best_delta is None or delta < best_delta):
            best = row
            best_delta = delta
    return best


def _assign_amounts(rows: list[dict[str, Any]], amounts: list[dict[str, Any]], median_height: float) -> None:
    max_delta = max(16.0, median_height * 0.72)
    for amount in sorted(amounts, key=_sort_key):
        value = _amount_value(amount.get('text'))
        amount_y = float(amount.get('center_y') or 0)
        assigned_row = None
        if value is not None and value < 0:
            assigned_row = _nearest_discount_row(rows, amount_y, max_delta)
        else:
            prev = _previous_label_row(rows, amount_y)
            if prev is not None and abs(amount_y - float(prev['center_y'])) <= max_delta:
                assigned_row = prev
            if assigned_row is None:
                candidates = [row for row in rows if not row.get('is_discount_context')]
                assigned_row = min(candidates, key=lambda row: abs(amount_y - float(row['center_y'])), default=None)
                if assigned_row is not None and abs(amount_y - float(assigned_row['center_y'])) > max_delta:
                    assigned_row = None
        if assigned_row is None:
            continue
        assigned_row['amounts'].append({
            'text': _norm(amount.get('text')),
            'value': value,
            'min_x': float(amount.get('min_x') or 0),
        })
    for row in rows:
        row['amounts'].sort(key=lambda item: float(item.get('min_x') or 0))


def _classify_row(row: dict[str, Any]) -> str:
    label = str(row.get('label') or '').lower()
    amounts = row.get('amounts') or []
    if any(token in label for token in _DISCOUNT_TOKENS):
        return 'discount' if any(item.get('value') is not None and item.get('value') < 0 for item in amounts) else 'invalid_discount'
    if not amounts:
        return 'missing_amount'
    if len(amounts) == 1:
        return 'single_article'
    if len(amounts) == 2 and label.strip().startswith('2x '):
        return 'quantity_unit_and_line_total'
    return 'multi_amount_review_needed'


def _render_row(row: dict[str, Any]) -> str:
    amount_text = ' '.join(str(amount.get('text')) for amount in (row.get('amounts') or []))
    return _norm(f"{row.get('label')} {amount_text}")


def _reconstruct_article_block(fragments: list[dict[str, Any]]) -> list[str] | None:
    heights = [float(item.get('height')) for item in fragments if float(item.get('height') or 0) > 0]
    median_height = median(heights) if heights else 27.0
    _start_y, _stop_y, block = _detect_article_block(fragments)
    if len(block) < 8:
        return None
    rows = _group_labels(block, median_height)
    amounts = _amount_fragments(block)
    if len(rows) < 5 or len(amounts) < 5:
        return None
    _assign_amounts(rows, amounts, median_height)
    classifications = [_classify_row(row) for row in rows]
    invalid = [kind for kind in classifications if kind in {'missing_amount', 'invalid_discount', 'multi_amount_review_needed'}]
    valid_articles = [kind for kind in classifications if kind in {'single_article', 'quantity_unit_and_line_total'}]
    if invalid or len(valid_articles) < 5:
        return None
    rendered = [_render_row(row) for row in rows]
    if not any('plus geeft' in line.lower() for line in rendered):
        return None
    return rendered


def _replace_article_block(current_lines: list[str], reconstructed_article_lines: list[str]) -> list[str] | None:
    start_index = None
    for index, line in enumerate(current_lines):
        lowered = line.lower()
        if any(token in lowered for token in _START_TOKENS):
            start_index = index + 1
            break
    if start_index is None:
        # Fallback for OCR variants where the header is split or missing: first product-ish line after header area.
        for index, line in enumerate(current_lines):
            if _ARTICLE_HINT_RE.search(line) and _AMOUNT_TOKEN_RE.search(line):
                start_index = index
                break
    if start_index is None:
        return None
    stop_index = None
    for index in range(start_index, len(current_lines)):
        lowered = current_lines[index].lower()
        if any(token in lowered for token in _STOP_TOKENS):
            stop_index = index
            break
    if stop_index is None or stop_index <= start_index:
        return None
    return current_lines[:start_index] + reconstructed_article_lines + current_lines[stop_index:]


def diagnose_plus_photo_line_grouping_fallback(
    *,
    filename: str,
    texts: list[str],
    boxes: list[Any],
    current_lines: list[str],
) -> dict[str, Any]:
    suffix = Path(filename or '').suffix.lower()
    diagnostics: dict[str, Any] = {
        'filename': filename,
        'suffix': suffix,
        'is_image_receipt': suffix in _IMAGE_EXTENSIONS,
        'has_texts': bool(texts),
        'text_count': len(texts or []),
        'has_boxes': bool(boxes),
        'box_count': len(boxes or []),
        'texts_boxes_same_length': bool(texts and boxes and len(texts) == len(boxes)),
        'looks_like_plus_receipt': False,
        'has_suspicious_article_merges': False,
        'article_block_detected': False,
        'article_block_fragment_count': 0,
        'reconstruction_valid': False,
        'replacement_valid': False,
        'fallback_applied': False,
        'fallback_reject_reason': None,
        'current_lines_before_fallback': list(current_lines or []),
        'raw_texts_sample': [_norm(text) for text in (texts or [])[:80]],
        'reconstructed_article_lines': [],
        'final_lines_after_fallback': list(current_lines or []),
    }
    if not diagnostics['is_image_receipt']:
        diagnostics['fallback_reject_reason'] = 'not_image_receipt'
        return diagnostics
    if not diagnostics['texts_boxes_same_length']:
        diagnostics['fallback_reject_reason'] = 'missing_or_mismatched_texts_boxes'
        return diagnostics
    diagnostics['looks_like_plus_receipt'] = _looks_like_plus_receipt(texts)
    if not diagnostics['looks_like_plus_receipt']:
        diagnostics['fallback_reject_reason'] = 'not_plus_profile'
        return diagnostics
    diagnostics['has_suspicious_article_merges'] = _has_suspicious_article_merges(current_lines)
    if not diagnostics['has_suspicious_article_merges']:
        diagnostics['fallback_reject_reason'] = 'no_suspicious_article_merges'
        return diagnostics
    fragments = _fragments_from_ocr(texts, boxes)
    _start_y, _stop_y, block = _detect_article_block(fragments)
    diagnostics['article_block_detected'] = bool(block)
    diagnostics['article_block_fragment_count'] = len(block)
    diagnostics['article_block_start_y'] = _start_y
    diagnostics['article_block_stop_y'] = _stop_y
    if not block:
        diagnostics['fallback_reject_reason'] = 'article_block_not_detected'
        return diagnostics
    reconstructed = _reconstruct_article_block(fragments)
    diagnostics['reconstructed_article_lines'] = list(reconstructed or [])
    diagnostics['reconstruction_valid'] = bool(reconstructed)
    if not reconstructed:
        diagnostics['fallback_reject_reason'] = 'reconstruction_invalid'
        return diagnostics
    replaced = _replace_article_block(current_lines, reconstructed)
    diagnostics['replacement_valid'] = bool(replaced and len(replaced) >= len(current_lines))
    if not diagnostics['replacement_valid']:
        diagnostics['fallback_reject_reason'] = 'replacement_invalid'
        return diagnostics
    diagnostics['fallback_applied'] = True
    diagnostics['fallback_reject_reason'] = None
    diagnostics['final_lines_after_fallback'] = list(replaced or [])
    return diagnostics


def apply_plus_photo_line_grouping_fallback(
    *,
    filename: str,
    texts: list[str],
    boxes: list[Any],
    current_lines: list[str],
) -> list[str] | None:
    """Return guarded PLUS image line reconstruction, or None when not safe.

    This is a store-profile fallback, not a receipt-specific fallback. It never
    checks concrete filenames or receipt IDs. It only activates for image OCR
    results with PLUS profile evidence, raw boxes, an article block, and proven
    suspicious current line merges.
    """
    diagnostics = diagnose_plus_photo_line_grouping_fallback(
        filename=filename,
        texts=texts,
        boxes=boxes,
        current_lines=current_lines,
    )
    if not diagnostics.get('fallback_applied'):
        return None
    return list(diagnostics.get('final_lines_after_fallback') or [])
