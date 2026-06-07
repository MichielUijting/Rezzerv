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
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

INPUT_JSON = Path('/tmp/rezzerv_raw_ocr_diagnostics/r9_38b2/raw_paddleocr_output_bounded.json')
OUTPUT_ROOT = Path('/tmp/rezzerv_raw_ocr_diagnostics/r9_38b5')
OUTPUT_JSON = OUTPUT_ROOT / 'hybrid_article_line_reconstruction_preview_v2.json'
AMOUNT_RE = re.compile(r'^[€CE]?-?\d{1,6}(?:[\.,]\d{2})(?:\s*EUR)?$', re.IGNORECASE)
ARTICLE_HINT_RE = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]{3,}')
START_TOKENS = ('omschrijving', 'onschrijving')
STOP_TOKENS = ('subtotaal', 'totaal', 'klantticket', 'terminal', 'betaling', 'btw groep', 'btw laag')
DISCOUNT_TOKENS = ('plus geeft', 'korting', 'actie', 'voordeel')
HEADER_TOKENS = ('omschrijving', 'onschrijving', 'p st/kg', 'bedrag')


def _norm(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _is_amount(text: Any) -> bool:
    return bool(AMOUNT_RE.fullmatch(_norm(text)))


def _amount_value(text: Any) -> float | None:
    raw = _norm(text).upper().replace('€', '').replace('EUR', '').strip()
    if raw.startswith('C') or raw.startswith('E'):
        raw = raw[1:]
    raw = raw.replace(',', '.')
    try:
        return float(Decimal(raw))
    except Exception:
        return None


def _is_text_label(fragment: dict[str, Any]) -> bool:
    text = _norm(fragment.get('text'))
    if not text or _is_amount(text):
        return False
    if not ARTICLE_HINT_RE.search(text):
        return False
    if text.lower().startswith('2ee'):
        return False
    return True


def _sort_key(fragment: dict[str, Any]) -> tuple[float, float, int]:
    return (float(fragment.get('center_y') or 0), float(fragment.get('min_x') or 0), int(fragment.get('global_index') or 0))


def _line_key(fragment: dict[str, Any]) -> str:
    return _norm(fragment.get('text')).lower()


def _detect_article_block(fragments: list[dict[str, Any]]) -> tuple[float, float, list[dict[str, Any]]]:
    ordered = sorted(fragments, key=_sort_key)
    start_y = None
    for item in ordered:
        text = _line_key(item)
        if any(token in text for token in START_TOKENS):
            start_y = float(item.get('center_y') or 0)
            break
    if start_y is None:
        for item in ordered:
            if _is_text_label(item) and float(item.get('center_y') or 0) > 300:
                start_y = float(item.get('center_y') or 0) - 30
                break
    stop_y = None
    for item in ordered:
        y = float(item.get('center_y') or 0)
        if start_y is not None and y <= start_y:
            continue
        text = _line_key(item)
        if any(token in text for token in STOP_TOKENS):
            stop_y = y
            break
    if start_y is None:
        start_y = 0.0
    if stop_y is None:
        stop_y = max((float(item.get('center_y') or 0) for item in ordered), default=start_y)
    block = [item for item in ordered if start_y < float(item.get('center_y') or 0) < stop_y]
    return start_y, stop_y, block


def _group_labels(block: list[dict[str, Any]], median_height: float) -> list[dict[str, Any]]:
    labels = [item for item in block if _is_text_label(item) and not any(token in _line_key(item) for token in HEADER_TOKENS)]
    rows: list[dict[str, Any]] = []
    # Keep physical article lines separate. Only merge fragments on nearly identical y.
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
                'is_discount_context': any(token in text.lower() for token in DISCOUNT_TOKENS),
            })
        else:
            best['label_fragments'].append(fragment)
            ordered = sorted(best['label_fragments'], key=lambda item: float(item.get('min_x') or 0))
            best['label'] = _norm(' '.join(_norm(item.get('text')) for item in ordered))
            best['center_y'] = median(float(item.get('center_y') or 0) for item in ordered)
            best['min_x'] = min(float(item.get('min_x') or 0) for item in ordered)
            best['max_x'] = max(float(item.get('max_x') or 0) for item in ordered)
            best['is_discount_context'] = any(token in best['label'].lower() for token in DISCOUNT_TOKENS)
    return sorted(rows, key=lambda row: float(row['center_y']))


def _amount_fragments(block: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in block if _is_amount(item.get('text'))]


def _new_row(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, 'amounts': [], 'assignment_notes': []}


def _previous_label_row(rows: list[dict[str, Any]], amount_y: float) -> dict[str, Any] | None:
    candidates = [row for row in rows if float(row['center_y']) <= amount_y]
    return candidates[-1] if candidates else None


def _nearest_discount_row(rows: list[dict[str, Any]], amount_y: float, max_delta: float) -> tuple[dict[str, Any] | None, float | None]:
    best = None
    best_delta = None
    for row in rows:
        if not row.get('is_discount_context'):
            continue
        delta = abs(amount_y - float(row['center_y']))
        if delta <= max_delta and (best_delta is None or delta < best_delta):
            best = row
            best_delta = delta
    return best, best_delta


def _assign_amounts_v2(label_rows: list[dict[str, Any]], amounts: list[dict[str, Any]], median_height: float) -> list[dict[str, Any]]:
    rows = [_new_row(row) for row in label_rows]
    if not rows:
        return rows
    max_delta = max(16.0, median_height * 0.72)
    for amount in sorted(amounts, key=_sort_key):
        text = _norm(amount.get('text'))
        value = _amount_value(text)
        amount_y = float(amount.get('center_y') or 0)
        assigned_row = None
        assignment_rule = ''
        delta = None

        if value is not None and value < 0:
            assigned_row, delta = _nearest_discount_row(rows, amount_y, max_delta)
            assignment_rule = 'negative_amount_to_nearest_discount_label'
        else:
            prev = _previous_label_row(rows, amount_y)
            if prev is not None:
                assigned_row = prev
                delta = abs(amount_y - float(prev['center_y']))
                assignment_rule = 'positive_amount_to_preceding_label_when_between_label_rows'
            if assigned_row is None or delta is None or delta > max_delta:
                # Conservative fallback: nearest non-discount label only.
                best = None
                best_delta = None
                for row in rows:
                    if row.get('is_discount_context'):
                        continue
                    d = abs(amount_y - float(row['center_y']))
                    if d <= max_delta and (best_delta is None or d < best_delta):
                        best = row
                        best_delta = d
                assigned_row = best
                delta = best_delta
                assignment_rule = 'positive_amount_to_nearest_non_discount_label_fallback'

        if assigned_row is None:
            continue
        assigned_row['amounts'].append({
            'text': text,
            'value': value,
            'center_y': amount.get('center_y'),
            'min_x': amount.get('min_x'),
            'max_x': amount.get('max_x'),
            'source_global_index': amount.get('global_index'),
            'delta_y_to_label': round(float(delta or 0), 3),
            'assignment_rule': assignment_rule,
        })
        assigned_row['assignment_notes'].append({
            'amount_text': text,
            'assignment_rule': assignment_rule,
            'delta_y_to_label': round(float(delta or 0), 3),
        })

    for row in rows:
        row['amounts'] = sorted(row['amounts'], key=lambda item: float(item.get('min_x') or 0))
    return rows


def _render_line(row: dict[str, Any]) -> str:
    amounts = row.get('amounts') or []
    amount_text = ' '.join(str(item.get('text')) for item in amounts)
    return _norm(f"{row.get('label')} {amount_text}")


def _classify_row(row: dict[str, Any]) -> str:
    label = str(row.get('label') or '').lower()
    amounts = row.get('amounts') or []
    if any(token in label for token in DISCOUNT_TOKENS):
        if any((item.get('value') is not None and item.get('value') < 0) for item in amounts):
            return 'discount_or_action_line'
        return 'discount_or_action_line_without_negative_amount'
    if len(amounts) == 0:
        return 'label_without_amount'
    if len(amounts) == 1:
        return 'single_article_line'
    if len(amounts) == 2 and str(row.get('label') or '').strip().lower().startswith('2x '):
        return 'quantity_unit_and_line_total_article_line'
    return 'multi_amount_review_needed'


def _expected_preview_hits(rows: list[dict[str, Any]]) -> dict[str, bool]:
    rendered = [_render_line(row).lower() for row in rows]
    return {
        'bami_nasi_mix': any('bami nasi mix' in line and ('1.69' in line or '1,69' in line) for line in rendered),
        'romige_kwark_kaneelb': any('ronige kwark kaneelb' in line and '2,05' in line for line in rendered),
        'romige_kwark_wit': any('romige kwark wit' in line and '2,05' in line for line in rendered),
        'strawberry_schnitte': any('strawberry schnitte' in line and '1,99' in line for line in rendered),
        'wereldger_teriyaki': any('wereldger. teriyaki' in line and '2,97' in line and '5,94' in line for line in rendered),
        'wereldger_zafr_bobo': any('wereldger.z-afr' in line and '2,97' in line and '5,94' in line for line in rendered),
        'bonenmix_mais': any('bonenmix mais' in line and '1,33' in line for line in rendered),
        'kikkererwten_bio': any('kikkererwten bio' in line and '1,22' in line for line in rendered),
        'kikkerwten': any('kikkerwten' in line and '1,02' in line for line in rendered),
        'cashewnoten': any('cashewnoten ongezout' in line and '2,05' in line and '1,02' not in line for line in rendered),
        'discount_050': any('plus geeft' in line and '-0.50' in line for line in rendered),
        'discount_016': any('plus geeft' in line and '-0,16' in line for line in rendered),
    }


def build_report() -> dict[str, Any]:
    started = time.perf_counter()
    if not INPUT_JSON.exists():
        raise RuntimeError(f'Missing input JSON: {INPUT_JSON}. Run R9-38B2b first.')
    data = json.loads(INPUT_JSON.read_text(encoding='utf-8'))
    fragments = [dict(item) for item in data.get('raw_fragment_table') or []]
    heights = [float(item.get('height')) for item in fragments if isinstance(item.get('height'), (int, float)) and float(item.get('height')) > 0]
    median_height = median(heights) if heights else 27.0
    start_y, stop_y, block = _detect_article_block(fragments)
    labels = _group_labels(block, median_height)
    amounts = _amount_fragments(block)
    reconstructed = _assign_amounts_v2(labels, amounts, median_height)
    rows = []
    for index, row in enumerate(reconstructed):
        rows.append({
            'index': index,
            'label': row.get('label'),
            'center_y': row.get('center_y'),
            'classification': _classify_row(row),
            'amounts': row.get('amounts') or [],
            'rendered_line': _render_line(row),
            'label_source_global_indexes': [item.get('global_index') for item in row.get('label_fragments') or []],
            'assignment_notes': row.get('assignment_notes') or [],
        })
    result = {
        'test': 'R9-38B5 hybrid article-line reconstruction preview v2',
        'read_only': True,
        'database_write_intent': False,
        'ocr_invoked': False,
        'parser_invoked': False,
        'runtime_change': False,
        'input_json': str(INPUT_JSON),
        'target': data.get('target'),
        'source_variant': data.get('source_variant'),
        'parameters': {
            'median_box_height': median_height,
            'article_block_start_y': start_y,
            'article_block_stop_y': stop_y,
            'amount_pairing_max_delta_y': max(16.0, median_height * 0.72),
            'method': 'positive right-column amounts attach to preceding label row; negative amounts attach to nearest discount/action row; 2X rows keep unit price plus line total',
        },
        'article_block_fragment_count': len(block),
        'article_block_amount_fragment_count': len(amounts),
        'reconstructed_article_lines': rows,
        'rendered_article_block_preview': [row['rendered_line'] for row in rows],
        'expected_preview_hits': _expected_preview_hits(reconstructed),
        'review_needed_lines': [row for row in rows if row['classification'] in ('label_without_amount', 'multi_amount_review_needed', 'discount_or_action_line_without_negative_amount')],
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
        'article_line_count': len(report['reconstructed_article_lines']),
        'expected_preview_hits': report['expected_preview_hits'],
        'review_needed_count': len(report['review_needed_lines']),
        'rendered_article_block_preview': report['rendered_article_block_preview'],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
