"""PLUS bounding-box article-line reconstruction diagnostics.

Diagnose-only module.

Purpose:
- reconstruct PLUS article lines from Paddle OCR fragments and bounding boxes;
- use the right amount column as row anchor;
- prevent reuse of labels and unit prices across neighbouring rows;
- avoid bundling closely stacked receipt rows through broad y-grouping;
- keep statiegeld as non-article financial row;
- do not alter parser output or database state.

No hardcoded article names, receipt IDs, filenames or receipt-specific prices.
"""

from __future__ import annotations

import re
from statistics import median
from typing import Any


_MONEY_RE = re.compile(r'[-€£CEe]?\s*\d{1,6}(?:[.,]\s?\d{2})')
_SPLIT_DECIMAL_HEAD_RE = re.compile(r'^\s*[-€£CEe]?\s*\d+[.,]\s*$')
_SPLIT_DECIMAL_TAIL_RE = re.compile(r'^\s*\d{2}\s*$')
_LETTER_RE = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]')
_WORD_RE = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]{3,}')
_HEADER_RE = re.compile(
    r'(?:omschrijving|onschrijving|dnschrijving|beschrijving).*(?:bedrag|p\.?\s*st|st/kg|p\s*st/kg)',
    re.IGNORECASE,
)
_SUBTOTAL_RE = re.compile(r'\bsubtotaal\b', re.IGNORECASE)
_TOTAL_RE = re.compile(r'\b(?:totaal|totael|yotaal|lotaal)\b', re.IGNORECASE)
_ARTICLE_BLOCK_NOISE_RE = re.compile(
    r'\b(?:klant|spaarkaart|geregistreerd)\b|^[*.=\-\s]+$',
    re.IGNORECASE,
)
_NON_ARTICLE_FINANCIAL_RE = re.compile(
    r'\b(?:statiegeld|pluspunten|digitale\s+zegels|zegel|zegels|mepal|buitenservies|buitensservies)\b',
    re.IGNORECASE,
)
_UNIT_ONLY_RE = re.compile(
    r'^\s*[-€£CEe]?\s*\d{1,6}(?:[.,]\s?\d{2})\s*(?:e\s*/?\s*kg|c\s*/?\s*kg|€/kg|kg|p\.?\s*st)?\s*$',
    re.IGNORECASE,
)


def _normalize(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _bbox_rect(box: Any) -> tuple[float, float, float, float] | None:
    try:
        if isinstance(box, (list, tuple)) and len(box) == 4 and not isinstance(box[0], (list, tuple)):
            x1, y1, x2, y2 = [float(v) for v in box]
            return x1, y1, x2, y2

        points: list[tuple[float, float]] = []
        for point in box:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append((float(point[0]), float(point[1])))

        if not points:
            return None

        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return min(xs), min(ys), max(xs), max(ys)
    except Exception:
        return None


def _fragment_from_text_box(index: int, text: Any, box: Any) -> dict[str, Any] | None:
    value = _normalize(text)
    if not value:
        return None

    rect = _bbox_rect(box)
    if rect is None:
        x1 = float(index)
        y1 = float(index * 20)
        x2 = x1 + 1.0
        y2 = y1 + 10.0
    else:
        x1, y1, x2, y2 = rect

    height = max(1.0, y2 - y1)

    return {
        'idx': index,
        'text': value,
        'x1': x1,
        'y1': y1,
        'x2': x2,
        'y2': y2,
        'cx': (x1 + x2) / 2.0,
        'cy': (y1 + y2) / 2.0,
        'height': height,
        'amounts': _MONEY_RE.findall(value),
        'has_letters': bool(_LETTER_RE.search(value)),
    }


def _merge_split_decimal_fragments(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(fragments, key=lambda item: (item['cy'], item['x1']))
    used: set[int] = set()
    merged: list[dict[str, Any]] = []

    for pos, current in enumerate(ordered):
        if pos in used:
            continue

        text = current['text']
        if not _SPLIT_DECIMAL_HEAD_RE.match(text):
            merged.append(current)
            continue

        best_next_pos = None
        best_score = None

        for next_pos in range(pos + 1, min(pos + 5, len(ordered))):
            candidate = ordered[next_pos]
            if next_pos in used:
                continue
            if not _SPLIT_DECIMAL_TAIL_RE.match(candidate['text']):
                continue

            y_gap = abs(candidate['cy'] - current['cy'])
            x_gap = abs(candidate['x1'] - current['x2'])
            if y_gap > max(12.0, current['height'] * 1.2):
                continue
            if x_gap > 18.0:
                continue

            score = y_gap + x_gap
            if best_score is None or score < best_score:
                best_score = score
                best_next_pos = next_pos

        if best_next_pos is None:
            merged.append(current)
            continue

        nxt = ordered[best_next_pos]
        used.add(best_next_pos)

        combined = dict(current)
        combined['text'] = f"{current['text'].strip()}{nxt['text'].strip()}"
        combined['x1'] = min(current['x1'], nxt['x1'])
        combined['y1'] = min(current['y1'], nxt['y1'])
        combined['x2'] = max(current['x2'], nxt['x2'])
        combined['y2'] = max(current['y2'], nxt['y2'])
        combined['cx'] = (combined['x1'] + combined['x2']) / 2.0
        combined['cy'] = (combined['y1'] + combined['y2']) / 2.0
        combined['height'] = max(1.0, combined['y2'] - combined['y1'])
        combined['amounts'] = _MONEY_RE.findall(combined['text'])
        combined['has_letters'] = bool(_LETTER_RE.search(combined['text']))
        combined['idx'] = current['idx']
        merged.append(combined)

    return sorted(merged, key=lambda item: (item['cy'], item['x1']))


def _group_for_bounds(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not fragments:
        return []

    heights = [fragment['height'] for fragment in fragments if fragment.get('height')]
    threshold = max(12.0, (median(heights) if heights else 12.0) * 0.7)

    ordered = sorted(fragments, key=lambda item: (item['cy'], item['x1']))
    groups: list[list[dict[str, Any]]] = []

    for fragment in ordered:
        if not groups:
            groups.append([fragment])
            continue

        current_group = groups[-1]
        current_y = sum(part['cy'] for part in current_group) / len(current_group)

        if abs(fragment['cy'] - current_y) <= threshold:
            current_group.append(fragment)
        else:
            groups.append([fragment])

    result: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        group = sorted(group, key=lambda item: item['x1'])
        text = _normalize(' '.join(part['text'] for part in group))
        result.append({
            'index': index,
            'text': text,
            'cy_min': min(part['cy'] for part in group),
            'cy_max': max(part['cy'] for part in group),
            'y1_min': min(part['y1'] for part in group),
            'y2_max': max(part['y2'] for part in group),
            'fragments': group,
        })

    return result


def _find_article_y_bounds(fragments: list[dict[str, Any]]) -> tuple[float, float, dict[str, Any]]:
    groups = _group_for_bounds(fragments)

    start_y = min((fragment['y1'] for fragment in fragments), default=0.0)
    end_y = max((fragment['y2'] for fragment in fragments), default=0.0)

    header_group = None
    subtotal_group = None

    for group in groups:
        if _HEADER_RE.search(group['text']):
            header_group = group
            start_y = group['y2_max'] + 1.0
            break

    for group in groups:
        if group['y1_min'] <= start_y:
            continue
        if _SUBTOTAL_RE.search(group['text']):
            subtotal_group = group
            end_y = group['y1_min'] - 1.0
            break

    return start_y, end_y, {
        'header_text': header_group['text'] if header_group else None,
        'subtotal_text': subtotal_group['text'] if subtotal_group else None,
        'header_y': header_group['y2_max'] if header_group else None,
        'subtotal_y': subtotal_group['y1_min'] if subtotal_group else None,
    }


def _is_noise_text(value: str) -> bool:
    text = _normalize(value)
    if not text:
        return True
    if _ARTICLE_BLOCK_NOISE_RE.search(text):
        return True
    if _HEADER_RE.search(text) or _SUBTOTAL_RE.search(text) or _TOTAL_RE.search(text):
        return True
    return False


def _is_pure_amount_fragment(fragment: dict[str, Any]) -> bool:
    text = fragment['text'].strip()
    return bool(_MONEY_RE.fullmatch(text)) and not fragment['has_letters']


def _is_unit_only_fragment(fragment: dict[str, Any]) -> bool:
    text = _normalize(fragment.get('text'))
    if not text:
        return False
    return bool(_UNIT_ONLY_RE.match(text))


def _is_label_candidate(fragment: dict[str, Any]) -> bool:
    text = _normalize(fragment.get('text'))
    if _is_noise_text(text):
        return False
    if not fragment.get('has_letters'):
        return False

    if _is_unit_only_fragment(fragment):
        return False

    words = _WORD_RE.findall(text)
    if len(words) >= 1:
        return True

    return False


def _clean_label_text(value: str) -> str:
    text = _normalize(value)
    text = re.sub(r'\s+', ' ', text)
    return text.strip(' .:-')


def _last_amount_text(value: str) -> str | None:
    matches = list(_MONEY_RE.finditer(value or ''))
    if not matches:
        return None
    return matches[-1].group(0).strip()


def _choose_right_amount_anchors(article_fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    amount_fragments = [
        fragment for fragment in article_fragments
        if _is_pure_amount_fragment(fragment)
    ]

    if not amount_fragments:
        return []

    max_cx = max(fragment['cx'] for fragment in amount_fragments)
    right_threshold = max_cx - 45.0

    anchors = [
        fragment for fragment in amount_fragments
        if fragment['cx'] >= right_threshold
    ]

    return sorted(anchors, key=lambda item: (item['cy'], item['x1']))


def _score_label_for_anchor(
    anchor: dict[str, Any],
    label: dict[str, Any],
    used_label_indexes: set[int],
) -> float | None:
    if label['idx'] in used_label_indexes:
        return None

    if label['x1'] >= anchor['x1'] - 8.0:
        return None

    row_tolerance = max(9.0, anchor['height'] * 0.75)
    y_distance = abs(label['cy'] - anchor['cy'])

    if y_distance > row_tolerance:
        return None

    x_distance = max(0.0, anchor['x1'] - label['x2'])

    # Small penalty for labels much farther left, but y-position dominates.
    return (y_distance * 10.0) + (x_distance * 0.03)


def _nearest_label_fragment(
    anchor: dict[str, Any],
    article_fragments: list[dict[str, Any]],
    used_label_indexes: set[int],
) -> dict[str, Any] | None:
    candidates: list[tuple[float, dict[str, Any]]] = []

    for fragment in article_fragments:
        if fragment is anchor:
            continue
        if not _is_label_candidate(fragment):
            continue

        score = _score_label_for_anchor(anchor, fragment, used_label_indexes)
        if score is None:
            continue

        candidates.append((score, fragment))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _nearest_unit_fragment(
    anchor: dict[str, Any],
    label: dict[str, Any] | None,
    article_fragments: list[dict[str, Any]],
    anchor_indexes: set[int],
    used_unit_indexes: set[int],
) -> dict[str, Any] | None:
    if label is None:
        return None

    candidates: list[tuple[float, float, dict[str, Any]]] = []

    # Stricter than label matching to avoid borrowing the unit price from a row above/below.
    unit_row_tolerance = max(7.0, anchor['height'] * 0.45)
    label_x2 = label['x2']

    for fragment in article_fragments:
        if fragment is anchor or fragment is label:
            continue
        if fragment['idx'] in used_unit_indexes:
            continue
        if fragment['idx'] in anchor_indexes:
            continue
        if not fragment.get('amounts'):
            continue
        if not _is_unit_only_fragment(fragment):
            continue

        if fragment['x1'] < label_x2 - 5.0:
            continue
        if fragment['x2'] >= anchor['x1'] + 5.0:
            continue

        y_distance = abs(fragment['cy'] - anchor['cy'])
        if y_distance > unit_row_tolerance:
            continue

        x_distance = max(0.0, anchor['x1'] - fragment['x2'])
        candidates.append((y_distance, x_distance, fragment))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def diagnose_plus_bbox_article_reconstruction(
    texts: list[Any],
    boxes: list[Any],
) -> dict[str, Any]:
    raw_fragments: list[dict[str, Any]] = []

    for index, text in enumerate(texts or []):
        box = boxes[index] if boxes is not None and index < len(boxes) else None
        fragment = _fragment_from_text_box(index, text, box)
        if fragment is not None:
            raw_fragments.append(fragment)

    fragments = _merge_split_decimal_fragments(raw_fragments)
    start_y, end_y, bounds = _find_article_y_bounds(fragments)

    article_fragments = [
        fragment for fragment in fragments
        if fragment['cy'] >= start_y and fragment['cy'] <= end_y
    ]

    anchors = _choose_right_amount_anchors(article_fragments)
    anchor_indexes = {anchor['idx'] for anchor in anchors}

    rows: list[dict[str, Any]] = []
    used_label_indexes: set[int] = set()
    used_unit_indexes: set[int] = set()

    for anchor in anchors:
        label = _nearest_label_fragment(anchor, article_fragments, used_label_indexes)
        unit = _nearest_unit_fragment(anchor, label, article_fragments, anchor_indexes, used_unit_indexes)

        if label is None:
            continue

        label_text = _clean_label_text(label['text'])
        unit_text = _clean_label_text(unit['text']) if unit is not None else ''
        amount_text = _last_amount_text(anchor['text']) or anchor['text']

        if not label_text:
            continue

        classification = 'non_article_financial' if _NON_ARTICLE_FINANCIAL_RE.search(label_text) else 'article_candidate'

        reconstructed_parts = [label_text]
        if unit_text and unit_text not in label_text:
            reconstructed_parts.append(unit_text)
        reconstructed_parts.append(amount_text)

        rows.append({
            'classification': classification,
            'reconstructed_line': _normalize(' '.join(reconstructed_parts)),
            'label': label_text,
            'unit_or_weight': unit_text or None,
            'amount': amount_text,
            'anchor_idx': anchor['idx'],
            'label_idx': label['idx'],
            'unit_idx': unit['idx'] if unit is not None else None,
            'anchor_y': round(anchor['cy'], 1),
            'label_y': round(label['cy'], 1),
            'unit_y': round(unit['cy'], 1) if unit is not None else None,
            'y_delta_label': round(abs(label['cy'] - anchor['cy']), 1),
            'source_fragments': {
                'label': label['text'],
                'unit_or_weight': unit['text'] if unit is not None else None,
                'amount': anchor['text'],
            },
        })

        used_label_indexes.add(label['idx'])
        if unit is not None:
            used_unit_indexes.add(unit['idx'])

    unused_text_fragments = [
        {
            'idx': fragment['idx'],
            'text': fragment['text'],
            'x1': round(fragment['x1'], 1),
            'x2': round(fragment['x2'], 1),
            'cy': round(fragment['cy'], 1),
        }
        for fragment in article_fragments
        if _is_label_candidate(fragment)
        and fragment['idx'] not in used_label_indexes
    ]

    unused_unit_fragments = [
        {
            'idx': fragment['idx'],
            'text': fragment['text'],
            'x1': round(fragment['x1'], 1),
            'x2': round(fragment['x2'], 1),
            'cy': round(fragment['cy'], 1),
        }
        for fragment in article_fragments
        if _is_unit_only_fragment(fragment)
        and fragment['idx'] not in used_unit_indexes
        and fragment['idx'] not in anchor_indexes
    ]

    return {
        'mode': 'diagnose_only',
        'version': 'PLUS-01G',
        'bounds': bounds,
        'fragment_count': len(fragments),
        'article_fragment_count': len(article_fragments),
        'right_amount_anchor_count': len(anchors),
        'rows': rows,
        'unused_text_fragments': unused_text_fragments,
        'unused_unit_fragments': unused_unit_fragments,
    }


__all__ = ['diagnose_plus_bbox_article_reconstruction']
