"""
Technical Design Reference:
- TD Section: TD-08 Test, baseline en regressie
- Module Role: Test or baseline support
- Runtime Type: test
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from statistics import median
from typing import Any

INPUT_JSON = Path('/tmp/rezzerv_raw_ocr_diagnostics/r9_38b2/raw_paddleocr_output_bounded.json')
OUTPUT_ROOT = Path('/tmp/rezzerv_raw_ocr_diagnostics/r9_38b3')
OUTPUT_JSON = OUTPUT_ROOT / 'line_grouping_strategy_preview.json'
AMOUNT_RE = re.compile(r'-?\d{1,6}(?:[\.,]\d{2})')
ARTICLE_RE = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]{3,}')
TARGET_TEXTS = (
    'RONIGE KWARK KANEELB',
    'ROMIGE KWARK WIT CHO',
    'STRAWBERRY SCHNITTE',
    '2X WERELDGER. TERIYAKI',
    '2X WERELDGER.Z-AFR B0BO',
    'BONENMIX MAIS',
    'KIKKERERWTEN BIO',
    'KIKKERWTEN',
    'CASHEWNOTEN ONGEZOUT',
)
PAYMENT_OR_TOTAL_TOKENS = (
    'totaal', 'subtotaal', 'btw', 'pin', 'betaling', 'terminal', 'merchant',
    'kaart', 'transactie', 'autorisatie', 'klantticket', 'leesmethode', 'maestro',
)


def _norm(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _amount_count(lines: list[str]) -> int:
    return sum(len(AMOUNT_RE.findall(line)) for line in lines)


def _article_like_count(lines: list[str]) -> int:
    count = 0
    for line in lines:
        lowered = line.lower()
        if any(token in lowered for token in PAYMENT_OR_TOTAL_TOKENS):
            continue
        if ARTICLE_RE.search(line) and AMOUNT_RE.search(line):
            count += 1
    return count


def _known_total_detected(lines: list[str], expected: str = '14,33') -> bool:
    return any(expected in line or expected.replace(',', '.') in line for line in lines)


def _fragment_sort_key(fragment: dict[str, Any]) -> tuple[float, float, int]:
    return (
        float(fragment.get('center_y') or 0),
        float(fragment.get('min_x') or 0),
        int(fragment.get('global_index') or 0),
    )


def _line_from_fragments(fragments: list[dict[str, Any]]) -> str:
    ordered = sorted(fragments, key=lambda item: (float(item.get('min_x') or 0), float(item.get('center_y') or 0)))
    return _norm(' '.join(str(item.get('text') or '') for item in ordered))


def _fragment_heights(fragments: list[dict[str, Any]]) -> list[float]:
    return [float(item.get('height')) for item in fragments if isinstance(item.get('height'), (int, float)) and float(item.get('height')) > 0]


def _current_grouping(data: dict[str, Any]) -> list[str]:
    return [_norm(line) for line in data.get('current_grouped_lines_for_comparison_only') or []]


def _group_by_y_threshold(fragments: list[dict[str, Any]], threshold: float) -> list[str]:
    rows: list[list[dict[str, Any]]] = []
    for fragment in sorted(fragments, key=_fragment_sort_key):
        center_y = float(fragment.get('center_y') or 0)
        best_row = None
        best_delta = None
        for row in rows:
            row_center = median(float(item.get('center_y') or 0) for item in row)
            delta = abs(center_y - row_center)
            if delta <= threshold and (best_delta is None or delta < best_delta):
                best_row = row
                best_delta = delta
        if best_row is None:
            rows.append([fragment])
        else:
            best_row.append(fragment)
    return [_line_from_fragments(row) for row in rows if _line_from_fragments(row)]


def _row_band_grouping(fragments: list[dict[str, Any]], band_height: float) -> list[str]:
    rows: list[list[dict[str, Any]]] = []
    for fragment in sorted(fragments, key=_fragment_sort_key):
        center_y = float(fragment.get('center_y') or 0)
        placed = False
        for row in rows:
            row_top = min(float(item.get('center_y') or 0) for item in row)
            row_bottom = max(float(item.get('center_y') or 0) for item in row)
            if row_top - band_height <= center_y <= row_bottom + band_height:
                row.append(fragment)
                placed = True
                break
        if not placed:
            rows.append([fragment])
    return [_line_from_fragments(row) for row in rows if _line_from_fragments(row)]


def _label_amount_pairing(fragments: list[dict[str, Any]]) -> list[str]:
    # Receipt-specific? No: generic column-aware rule. Left/middle text fragments are labels;
    # right-side money fragments attach to nearest label by y-distance.
    if not fragments:
        return []
    max_x = max(float(item.get('max_x') or 0) for item in fragments)
    amount_x_cutoff = max_x * 0.62
    labels = [item for item in fragments if not AMOUNT_RE.fullmatch(str(item.get('text') or '').strip()) or float(item.get('min_x') or 0) < amount_x_cutoff]
    amounts = [item for item in fragments if AMOUNT_RE.fullmatch(str(item.get('text') or '').strip()) and float(item.get('min_x') or 0) >= amount_x_cutoff]
    rows: list[list[dict[str, Any]]] = []
    for label in sorted(labels, key=_fragment_sort_key):
        text = str(label.get('text') or '')
        if not text.strip():
            continue
        rows.append([label])
    for amount in amounts:
        ay = float(amount.get('center_y') or 0)
        best_row: list[dict[str, Any]] | None = None
        best_delta: float | None = None
        for row in rows:
            # Avoid attaching article amounts to obvious headers/payment labels when a closer product label exists.
            row_text = _line_from_fragments(row).lower()
            row_center = median(float(item.get('center_y') or 0) for item in row)
            delta = abs(ay - row_center)
            if any(token in row_text for token in ('omschrijving', 'bedrag', 'btw groep')):
                delta += 20
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_row = row
        if best_row is not None:
            best_row.append(amount)
    return [_line_from_fragments(row) for row in rows if _line_from_fragments(row)]


def _bad_merges(lines: list[str]) -> list[dict[str, Any]]:
    suspected: list[dict[str, Any]] = []
    for line in lines:
        hits = [text for text in TARGET_TEXTS if text.lower() in line.lower()]
        if len(hits) >= 2:
            suspected.append({'line': line, 'matched_target_texts': hits, 'reason': 'multiple_target_article_labels_in_one_grouped_line'})
    return suspected


def _strategy_report(name: str, lines: list[str], current_lines: list[str], parameters: dict[str, Any]) -> dict[str, Any]:
    line_set = set(lines)
    current_set = set(current_lines)
    return {
        'strategy_name': name,
        'parameters': parameters,
        'grouped_lines': lines,
        'line_count': len(lines),
        'amount_token_count': _amount_count(lines),
        'article_like_line_count': _article_like_count(lines),
        'known_total_detected': _known_total_detected(lines),
        'suspected_bad_merges': _bad_merges(lines),
        'difference_vs_current_grouping': {
            'added_lines': sorted(line_set - current_set)[:120],
            'removed_lines': sorted(current_set - line_set)[:120],
            'added_count': len(line_set - current_set),
            'removed_count': len(current_set - line_set),
        },
    }


def _target_fragment_table(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for fragment in fragments:
        text = str(fragment.get('text') or '')
        if any(target.lower() in text.lower() for target in TARGET_TEXTS):
            rows.append({
                'text': text,
                'global_index': fragment.get('global_index'),
                'center_y': fragment.get('center_y'),
                'height': fragment.get('height'),
                'min_x': fragment.get('min_x'),
                'max_x': fragment.get('max_x'),
            })
    return rows


def build_report() -> dict[str, Any]:
    started = time.perf_counter()
    if not INPUT_JSON.exists():
        raise RuntimeError(f'Missing input JSON: {INPUT_JSON}. Run R9-38B2b first.')
    data = json.loads(INPUT_JSON.read_text(encoding='utf-8'))
    fragments = [dict(item) for item in data.get('raw_fragment_table') or []]
    heights = _fragment_heights(fragments)
    med_height = median(heights) if heights else 27.0
    current = _current_grouping(data)
    strict_threshold = round(med_height * 0.45, 3)
    row_band_height = round(med_height * 0.25, 3)
    strategies = [
        _strategy_report('current_grouping', current, current, {'source': 'R9-38B2b current_grouped_lines_for_comparison_only'}),
        _strategy_report('strict_y_grouping', _group_by_y_threshold(fragments, strict_threshold), current, {'threshold': strict_threshold, 'threshold_formula': 'median_box_height * 0.45', 'median_box_height': med_height}),
        _strategy_report('row_band_grouping', _row_band_grouping(fragments, row_band_height), current, {'band_height': row_band_height, 'band_formula': 'median_box_height * 0.25', 'median_box_height': med_height}),
        _strategy_report('label_amount_pairing', _label_amount_pairing(fragments), current, {'amount_column_cutoff_formula': 'max_x * 0.62', 'method': 'attach right-column amount fragments to nearest label center_y'}),
    ]
    result = {
        'test': 'R9-38B3 line grouping strategy preview',
        'read_only': True,
        'database_write_intent': False,
        'ocr_invoked': False,
        'parser_invoked': False,
        'input_json': str(INPUT_JSON),
        'target': data.get('target'),
        'source_variant': data.get('source_variant'),
        'fragment_count': len(fragments),
        'median_box_height': med_height,
        'target_article_fragment_evidence': _target_fragment_table(fragments),
        'strategies': strategies,
        'runtime_seconds': round(time.perf_counter() - started, 3),
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    result['output_json_path'] = str(OUTPUT_JSON)
    return result


def main() -> int:
    report = build_report()
    summary = {
        'test': report['test'],
        'status': 'ok',
        'output_json_path': report['output_json_path'],
        'runtime_seconds': report['runtime_seconds'],
        'fragment_count': report['fragment_count'],
        'strategies': [
            {
                'strategy_name': item['strategy_name'],
                'line_count': item['line_count'],
                'amount_token_count': item['amount_token_count'],
                'article_like_line_count': item['article_like_line_count'],
                'suspected_bad_merge_count': len(item['suspected_bad_merges']),
            }
            for item in report['strategies']
        ],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
