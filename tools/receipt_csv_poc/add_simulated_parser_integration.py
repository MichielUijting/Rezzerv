from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from add_amount_region_zone_diagnostics import _image_by_stem, _should_run_for_image

DEFAULT_TARGETS = {
    'AH foto 2',
    'AH foto 3',
    'Aldi foto 2',
    'Plus foto 2',
    'plus foto 1',
}
LOW_RISK_LEVEL = 'low'
MIN_CONSENSUS_WEIGHTED_SCORE = Decimal('0.82')
DUPLICATE_TEXT_SIMILARITY = 0.72
CONFLICT_TEXT_SIMILARITY = 0.55
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


def _norm(text: Any) -> str:
    text = str(text or '').lower()
    text = re.sub(r'[^a-z0-9à-ÿ]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _as_decimal(value: Any, default: Decimal = Decimal('0')) -> Decimal:
    try:
        if value is None or value == '':
            return default
        return Decimal(str(value).replace(',', '.')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        match = re.search(r'-?\d+(?:[\.,]\d{1,2})?', str(value or ''))
        if match:
            try:
                return Decimal(match.group(0).replace(',', '.')).quantize(Decimal('0.01'))
            except Exception:
                return default
    return default


def _amount_from_row(row: dict[str, Any]) -> Decimal:
    for key in ('amount', 'line_total', 'amount_text'):
        if key in row and row.get(key) not in (None, ''):
            return _as_decimal(row.get(key))
    amounts = row.get('amounts') or []
    if amounts:
        return _as_decimal(amounts[0])
    return Decimal('0')


def _text_from_parser_row(row: dict[str, Any]) -> str:
    return str(row.get('item_text') or row.get('product_name') or row.get('raw_line') or '').strip()


def _similarity(a: Any, b: Any) -> float:
    a_norm = _norm(a)
    b_norm = _norm(b)
    if not a_norm or not b_norm:
        return 0.0
    seq = SequenceMatcher(None, a_norm, b_norm).ratio()
    a_tokens = set(a_norm.split())
    b_tokens = set(b_norm.split())
    token_overlap = len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))
    return round((seq * 0.65) + (token_overlap * 0.35), 3)


def _existing_parser_rows(receipt_json: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in receipt_json.get('lines', []) or []:
        rows.append({
            'line_no': row.get('line_no'),
            'product_name': _text_from_parser_row(row),
            'amount': float(_amount_from_row(row)),
            'line_type': row.get('line_type'),
            'source': 'existing_parser_row',
            'raw_line': row.get('raw_line'),
            'parser_confidence': row.get('parser_confidence'),
            'warning': row.get('warning'),
        })
    return rows


def _source_weighted_rows(receipt_json: dict[str, Any]) -> list[dict[str, Any]]:
    weighted = receipt_json.get('metadata', {}).get('consensus_weighted_shadow_reconstruction', {})
    rows = []
    for row in weighted.get('weighted_rows', []) or []:
        score = _as_decimal(row.get('consensus_weighted_score'))
        risk = str(row.get('risk_level') or '').lower()
        if risk != LOW_RISK_LEVEL or score < MIN_CONSENSUS_WEIGHTED_SCORE:
            continue
        rows.append(row)
    return rows


def _classify_against_existing(candidate: dict[str, Any], existing: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None, str, float]:
    candidate_text = candidate.get('product_name') or candidate.get('product_cluster_text') or ''
    candidate_amount = _amount_from_row(candidate)
    best_same_amount = None
    best_same_amount_similarity = 0.0
    best_text = None
    best_text_similarity = 0.0
    for row in existing:
        row_text = row.get('product_name') or ''
        row_amount = _amount_from_row(row)
        sim = _similarity(candidate_text, row_text)
        if abs(candidate_amount - row_amount) <= AMOUNT_TOLERANCE and sim > best_same_amount_similarity:
            best_same_amount_similarity = sim
            best_same_amount = row
        if sim > best_text_similarity:
            best_text_similarity = sim
            best_text = row
    if best_same_amount is not None and best_same_amount_similarity >= DUPLICATE_TEXT_SIMILARITY:
        return 'duplicate', best_same_amount, 'same_amount_and_similar_product_text', best_same_amount_similarity
    if best_text is not None and best_text_similarity >= CONFLICT_TEXT_SIMILARITY:
        best_text_amount = _amount_from_row(best_text)
        if abs(candidate_amount - best_text_amount) > AMOUNT_TOLERANCE:
            return 'conflict', best_text, 'similar_product_text_different_amount', best_text_similarity
    return 'add', None, 'no_duplicate_or_conflict_with_existing_parser_rows', max(best_same_amount_similarity, best_text_similarity)


def build_simulated_parser_integration(receipt_json: dict[str, Any]) -> dict[str, Any]:
    existing = _existing_parser_rows(receipt_json)
    weighted_rows = _source_weighted_rows(receipt_json)
    simulated_added = []
    duplicate_candidates = []
    conflicts = []
    rejected_candidates = []

    for row in weighted_rows:
        classification, matched, reason, similarity = _classify_against_existing(row, existing)
        candidate = {
            'product_name': row.get('product_name'),
            'amount': float(_amount_from_row(row)),
            'amount_text': row.get('amount_text'),
            'amounts': row.get('amounts', []),
            'source': 'consensus_weighted_shadow_row',
            'consensus_weighted_score': row.get('consensus_weighted_score'),
            'risk_level': row.get('risk_level'),
            'base_reliability_score': row.get('base_reliability_score'),
            'consensus_confidence': row.get('consensus_confidence'),
            'route_support_count': row.get('route_support_count'),
            'simulation_reason': reason,
            'matched_existing_similarity': similarity,
            'diagnostic_only': True,
            'parser_output_changed': False,
            'csv_output_changed': False,
        }
        if classification == 'add':
            simulated_added.append(candidate)
        elif classification == 'duplicate':
            duplicate_candidates.append({
                **candidate,
                'matched_existing_parser_row': matched,
                'duplicate_reason': reason,
            })
        elif classification == 'conflict':
            conflicts.append({
                **candidate,
                'matched_existing_parser_row': matched,
                'conflict_reason': reason,
            })
        else:
            rejected_candidates.append({**candidate, 'reject_reason': 'unknown_classification'})

    existing_total = sum((_amount_from_row(row) for row in existing), Decimal('0'))
    added_total = sum((_amount_from_row(row) for row in simulated_added), Decimal('0'))
    simulated_total = existing_total + added_total
    return {
        'diagnostic_scope': 'simulated_parser_integration_from_consensus_weighted_shadow_rows',
        'diagnostic_only': True,
        'parser_output_changed': False,
        'csv_output_changed': False,
        'simulation_only': True,
        'existing_parser_rows': existing,
        'simulated_added_rows': simulated_added,
        'duplicate_candidates': duplicate_candidates,
        'conflicting_rows': conflicts,
        'rejected_candidates': rejected_candidates,
        'integration_diff': {
            'existing_parser_row_count': len(existing),
            'source_consensus_weighted_low_risk_count': len(weighted_rows),
            'added_row_count': len(simulated_added),
            'duplicate_candidate_count': len(duplicate_candidates),
            'conflict_count': len(conflicts),
            'rejected_candidate_count': len(rejected_candidates),
            'existing_total': float(existing_total),
            'simulated_total_delta': float(added_total),
            'simulated_combined_total': float(simulated_total),
        },
        'rules': {
            'allowed_source': 'consensus_weighted_shadow_reconstruction.weighted_rows',
            'required_risk_level': LOW_RISK_LEVEL,
            'min_consensus_weighted_score': float(MIN_CONSENSUS_WEIGHTED_SCORE),
            'duplicate_text_similarity': DUPLICATE_TEXT_SIMILARITY,
            'conflict_text_similarity': CONFLICT_TEXT_SIMILARITY,
            'amount_tolerance': float(AMOUNT_TOLERANCE),
            'parser_input_changed': False,
            'csv_output_changed': False,
        },
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')
    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('simulated_parser_integration', {})
    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_simulated_parser_integration(payload)
        payload.setdefault('metadata', {})['simulated_parser_integration'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['simulated_parser_integration'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1
    summary['schema_version'] = 'receipt-ocr-benchmark-v35-simulated-parser-integration'
    summary['simulated_parser_integration_processed_receipts'] = processed
    summary['simulated_parser_integration_skipped_receipts'] = skipped
    summary['simulated_parser_integration_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Simulated parser integration diagnostics added for {processed} receipts; skipped={skipped}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='input_receipts')
    parser.add_argument('--output', default='')
    parser.add_argument('--latest-file', default='LATEST_PUSHED_RUN.txt')
    parser.add_argument('--targets', nargs='*', default=sorted(DEFAULT_TARGETS))
    args = parser.parse_args()
    output_dir = Path(args.output) if args.output else _read_latest_run_path(Path(args.latest_file))
    update_targeted_run(Path(args.input), output_dir, set(args.targets))


if __name__ == '__main__':
    main()
