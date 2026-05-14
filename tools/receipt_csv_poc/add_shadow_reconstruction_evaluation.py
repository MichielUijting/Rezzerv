from __future__ import annotations

import argparse
import csv
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from add_amount_region_zone_diagnostics import _image_by_stem, _should_run_for_image

DEFAULT_TARGETS = {
    'AH foto 2',
    'Aldi foto 2',
    'Plus foto 2',
    'plus foto 1',
}
BASELINE_NAME_HINTS = ('baseline', 'expected', 'verwacht', 'testoutput', 'kassabon')
SUPPORTED_BASELINE_EXTENSIONS = {'.csv', '.tsv', '.json', '.xlsx'}
AMOUNT_TOLERANCE = Decimal('0.01')


def _read_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding='utf-8').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    return values


def _candidate_run_paths(raw_run_path: str) -> list[Path]:
    raw = Path(raw_run_path)
    candidates = [raw]
    prefix = Path('tools') / 'receipt_csv_poc'
    prefix_parts = prefix.parts
    parts = raw.parts
    if len(parts) > len(prefix_parts) and parts[:len(prefix_parts)] == prefix_parts:
        candidates.append(Path(*parts[len(prefix_parts):]))
    if raw.name:
        candidates.append(Path('test_runs') / raw.name)
    return candidates


def _is_valid_run_dir(path: Path) -> bool:
    return (path / 'json').exists() and (path / 'benchmark_summary.json').exists()


def _find_latest_valid_run(test_runs_dir: Path = Path('test_runs')) -> Path:
    valid_runs = [path for path in test_runs_dir.glob('run_*') if path.is_dir() and _is_valid_run_dir(path)]
    if not valid_runs:
        raise FileNotFoundError(f'No valid run directory found under {test_runs_dir}')
    return sorted(valid_runs, key=lambda path: path.name)[-1]


def _read_latest_run_path(latest_file: Path) -> Path:
    values = _read_key_values(latest_file)
    raw_run_path = values.get('run_path', '')
    if raw_run_path:
        for candidate in _candidate_run_paths(raw_run_path):
            if _is_valid_run_dir(candidate):
                return candidate
        print(f'[WARN] LATEST_PUSHED_RUN points to invalid or incomplete run: {raw_run_path}')
    fallback = _find_latest_valid_run()
    print(f'[INFO] Using latest valid local run instead: {fallback}')
    return fallback


def _norm(value: Any) -> str:
    value = str(value or '').lower()
    value = re.sub(r'[^a-z0-9à-ÿ]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def _receipt_key(value: Any) -> str:
    text = _norm(value)
    for suffix in (' jpg', ' jpeg', ' png', ' webp', ' bmp', ' tiff', ' tif'):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text.strip()


def _amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace('€', '').replace('EUR', '').replace('eur', '').replace(' ', '')
    if not text:
        return None
    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '')
    else:
        text = text.replace(',', '.')
    match = re.search(r'-?\d+(?:\.\d{1,2})?', text)
    if not match:
        return None
    try:
        return Decimal(match.group(0)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def _similarity(a: str, b: str) -> float:
    a_tokens = set(_norm(a).split())
    b_tokens = set(_norm(b).split())
    if not a_tokens or not b_tokens:
        return 0.0
    intersection = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    return intersection / max(1, union)


def _find_baseline_file(explicit: str = '') -> Path | None:
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path
    search_roots = [Path('.'), Path('..'), Path('..') / '..']
    candidates: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob('*'):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_BASELINE_EXTENSIONS:
                continue
            name = path.name.lower()
            if any(hint in name for hint in BASELINE_NAME_HINTS) and 'test_runs' not in str(path).replace('\\', '/').lower():
                candidates.append(path)
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: (len(path.parts), path.name.lower()))[0]


def _row_get(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    normalized = {_norm(key): value for key, value in row.items()}
    for candidate in candidates:
        key = _norm(candidate)
        if key in normalized:
            return normalized[key]
    for key, value in normalized.items():
        for candidate in candidates:
            if _norm(candidate) in key:
                return value
    return None


def _rows_from_csv(path: Path) -> list[dict[str, Any]]:
    delimiter = '\t' if path.suffix.lower() == '.tsv' else ','
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def _rows_from_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ('rows', 'expected_rows', 'baseline_rows', 'receipts'):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _rows_from_xlsx(path: Path) -> list[dict[str, Any]]:
    try:
        import pandas as pd
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    try:
        sheets = pd.read_excel(path, sheet_name=None)
    except Exception:
        return []
    for sheet_name, dataframe in sheets.items():
        for record in dataframe.fillna('').to_dict(orient='records'):
            record['_sheet_name'] = sheet_name
            rows.append(record)
    return rows


def _read_baseline_rows(path: Path | None) -> tuple[list[dict[str, Any]], str]:
    if path is None:
        return [], 'no_baseline_file_found'
    suffix = path.suffix.lower()
    if suffix in {'.csv', '.tsv'}:
        rows = _rows_from_csv(path)
    elif suffix == '.json':
        rows = _rows_from_json(path)
    elif suffix == '.xlsx':
        rows = _rows_from_xlsx(path)
    else:
        rows = []
    return rows, str(path)


def _baseline_items_for_receipt(rows: list[dict[str, Any]], receipt_stem: str) -> list[dict[str, Any]]:
    receipt_key = _receipt_key(receipt_stem)
    items = []
    for row in rows:
        receipt_value = _row_get(row, ('receipt', 'source_file', 'bon', 'bestand', 'filename', 'file', 'image', 'afbeelding', 'kassabon'))
        sheet_value = row.get('_sheet_name')
        row_receipt = _receipt_key(receipt_value or sheet_value or '')
        if row_receipt and receipt_key and receipt_key not in row_receipt and row_receipt not in receipt_key:
            continue
        product = _row_get(row, ('product', 'product_name', 'artikel', 'artikelnaam', 'omschrijving', 'item', 'naam'))
        amount_value = _row_get(row, ('amount', 'bedrag', 'prijs', 'line_total', 'totaal', 'waarde'))
        amount = _amount(amount_value)
        if not product or amount is None:
            continue
        items.append({
            'product_name': str(product).strip(),
            'amount': str(amount),
            'source_receipt': row_receipt,
        })
    return items


def _shadow_items(receipt_json: dict) -> list[dict[str, Any]]:
    shadow = receipt_json.get('metadata', {}).get('shadow_reconstruction_output', {})
    items = []
    for row in shadow.get('generated_rows', []):
        amount = _amount(row.get('amount'))
        if amount is None:
            continue
        items.append({
            'product_name': row.get('product_name'),
            'amount': str(amount),
            'reliability_score': row.get('reliability_score'),
            'risk_level': row.get('risk_level'),
            'variant': row.get('variant'),
            'cluster_id': row.get('cluster_id'),
        })
    return items


def _match_items(shadow: list[dict[str, Any]], baseline: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    matched_baseline: set[int] = set()
    true_positives = []
    false_positives = []
    for shadow_row in shadow:
        shadow_amount = _amount(shadow_row.get('amount'))
        best_index = None
        best_score = 0.0
        for index, baseline_row in enumerate(baseline):
            if index in matched_baseline:
                continue
            baseline_amount = _amount(baseline_row.get('amount'))
            if shadow_amount is None or baseline_amount is None:
                continue
            if abs(shadow_amount - baseline_amount) > AMOUNT_TOLERANCE:
                continue
            similarity = _similarity(str(shadow_row.get('product_name') or ''), str(baseline_row.get('product_name') or ''))
            if similarity > best_score:
                best_score = similarity
                best_index = index
        if best_index is not None and best_score >= 0.20:
            matched_baseline.add(best_index)
            true_positives.append({
                'shadow_row': shadow_row,
                'baseline_row': baseline[best_index],
                'product_similarity': round(best_score, 3),
                'match_reason': 'same_amount_and_product_token_overlap',
            })
        else:
            false_positives.append({
                'shadow_row': shadow_row,
                'reject_reason': 'no_baseline_row_with_same_amount_and_product_overlap',
            })
    false_negatives = [row for index, row in enumerate(baseline) if index not in matched_baseline]
    return true_positives, false_positives, false_negatives


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def build_shadow_reconstruction_evaluation(receipt_json: dict, baseline_rows: list[dict[str, Any]], baseline_source: str) -> dict[str, object]:
    receipt_name = receipt_json.get('metadata', {}).get('source_file') or ''
    baseline = _baseline_items_for_receipt(baseline_rows, Path(str(receipt_name)).stem)
    shadow = _shadow_items(receipt_json)

    if not baseline_rows:
        return {
            'diagnostic_scope': 'shadow_reconstruction_precision_recall_evaluation',
            'diagnostic_only': True,
            'reconstruction_applied': False,
            'evaluation_available': False,
            'skip_reason': baseline_source,
            'metrics': {
                'true_positive_count': 0,
                'false_positive_count': 0,
                'false_negative_count': 0,
                'precision': 0.0,
                'recall': 0.0,
                'candidate_coverage': 0.0,
            },
            'unmatched_shadow_rows': shadow,
            'unmatched_baseline_rows': [],
        }

    true_pos, false_pos, false_neg = _match_items(shadow, baseline)
    tp = len(true_pos)
    fp = len(false_pos)
    fn = len(false_neg)
    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    candidate_coverage = _safe_ratio(len(shadow), len(baseline))
    return {
        'diagnostic_scope': 'shadow_reconstruction_precision_recall_evaluation',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'evaluation_available': True,
        'baseline_source': baseline_source,
        'baseline_row_count_for_receipt': len(baseline),
        'shadow_row_count_for_receipt': len(shadow),
        'metrics': {
            'true_positive_count': tp,
            'false_positive_count': fp,
            'false_negative_count': fn,
            'precision': precision,
            'recall': recall,
            'candidate_coverage': candidate_coverage,
        },
        'matched_rows': true_pos,
        'unmatched_shadow_rows': false_pos,
        'unmatched_baseline_rows': false_neg,
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str], baseline_path: str = '') -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    baseline_file = _find_baseline_file(baseline_path)
    baseline_rows, baseline_source = _read_baseline_rows(baseline_file)
    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('shadow_reconstruction_evaluation', {})

    processed = 0
    skipped = 0
    totals = {'tp': 0, 'fp': 0, 'fn': 0, 'shadow': 0, 'baseline': 0}
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_shadow_reconstruction_evaluation(payload, baseline_rows, baseline_source)
        payload.setdefault('metadata', {})['shadow_reconstruction_evaluation'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['shadow_reconstruction_evaluation'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        metrics = diagnostics.get('metrics', {})
        totals['tp'] += int(metrics.get('true_positive_count', 0) or 0)
        totals['fp'] += int(metrics.get('false_positive_count', 0) or 0)
        totals['fn'] += int(metrics.get('false_negative_count', 0) or 0)
        totals['shadow'] += int(diagnostics.get('shadow_row_count_for_receipt', 0) or 0)
        totals['baseline'] += int(diagnostics.get('baseline_row_count_for_receipt', 0) or 0)
        processed += 1

    summary['schema_version'] = 'receipt-ocr-benchmark-v28-shadow-reconstruction-evaluation'
    summary['shadow_reconstruction_evaluation_processed_receipts'] = processed
    summary['shadow_reconstruction_evaluation_skipped_receipts'] = skipped
    summary['shadow_reconstruction_evaluation_targeted_only'] = True
    summary['shadow_reconstruction_evaluation_baseline_source'] = baseline_source
    summary['shadow_reconstruction_evaluation_totals'] = {
        'true_positive_count': totals['tp'],
        'false_positive_count': totals['fp'],
        'false_negative_count': totals['fn'],
        'precision': _safe_ratio(totals['tp'], totals['tp'] + totals['fp']),
        'recall': _safe_ratio(totals['tp'], totals['tp'] + totals['fn']),
        'candidate_coverage': _safe_ratio(totals['shadow'], totals['baseline']),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Shadow reconstruction evaluation added for {processed} receipts; skipped={skipped}; baseline={baseline_source}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='input_receipts')
    parser.add_argument('--output', default='')
    parser.add_argument('--latest-file', default='LATEST_PUSHED_RUN.txt')
    parser.add_argument('--baseline', default='')
    parser.add_argument('--targets', nargs='*', default=sorted(DEFAULT_TARGETS))
    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else _read_latest_run_path(Path(args.latest_file))
    update_targeted_run(Path(args.input), output_dir, set(args.targets), args.baseline)


if __name__ == '__main__':
    main()
