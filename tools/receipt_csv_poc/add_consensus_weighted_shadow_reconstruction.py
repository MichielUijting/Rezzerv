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
LOW_RISK_MIN = Decimal('0.82')
MEDIUM_RISK_MIN = Decimal('0.62')


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


def _amount_key(value: Any, amounts: list[Any] | None = None) -> str:
    if amounts:
        text = str(amounts[0]).replace(',', '.').strip()
    else:
        text = str(value or '').replace(',', '.').strip()
    match = re.search(r'-?\d+(?:\.\d{1,2})?', text)
    if not match:
        return ''
    try:
        return str(Decimal(match.group(0)).quantize(Decimal('0.01')))
    except (InvalidOperation, ValueError):
        return match.group(0)


def _as_decimal(value: Any, default: Decimal = Decimal('0')) -> Decimal:
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _text_similarity(a: Any, b: Any) -> float:
    a_norm = _norm(a)
    b_norm = _norm(b)
    if not a_norm or not b_norm:
        return 0.0
    seq = SequenceMatcher(None, a_norm, b_norm).ratio()
    a_tokens = set(a_norm.split())
    b_tokens = set(b_norm.split())
    token_overlap = len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))
    return (seq * 0.65) + (token_overlap * 0.35)


def _risk(score: Decimal) -> str:
    if score >= LOW_RISK_MIN:
        return 'low'
    if score >= MEDIUM_RISK_MIN:
        return 'medium'
    return 'high'


def _find_consensus_match(row: dict[str, Any], consensus_groups: list[dict[str, Any]]) -> dict[str, Any] | None:
    row_text = row.get('product_name') or row.get('product_cluster_text') or ''
    row_amount = _amount_key(row.get('amount') or row.get('amount_text'), row.get('amounts'))
    best = None
    best_score = 0.0
    for group in consensus_groups:
        amount_candidates = [str(value) for value in group.get('amount_candidates', [])]
        amount_match = row_amount and row_amount in amount_candidates
        text_score = max((_text_similarity(row_text, text) for text in group.get('product_text_candidates', [])), default=0.0)
        score = text_score + (0.45 if amount_match else 0.0)
        if score > best_score:
            best_score = score
            best = group
    if best and best_score >= 0.68:
        return best
    return None


def _disagreement_penalty(row: dict[str, Any], disagreements: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    row_text = row.get('product_name') or row.get('product_cluster_text') or ''
    row_amount = _amount_key(row.get('amount') or row.get('amount_text'), row.get('amounts'))
    matches = []
    for disagreement in disagreements:
        amount_candidates = [str(value) for value in disagreement.get('amount_candidates', [])]
        product_candidates = disagreement.get('product_text_candidates', []) or []
        amount_match = row_amount and row_amount in amount_candidates
        text_match = max((_text_similarity(row_text, text) for text in product_candidates), default=0.0) >= 0.55
        if amount_match or text_match:
            matches.append(disagreement)
    penalty = min(0.18, len(matches) * 0.06)
    return penalty, matches[:5]


def _weighted_score(base: Decimal, consensus: dict[str, Any] | None, penalty: float) -> tuple[Decimal, str, float, int]:
    base_float = float(base)
    consensus_conf = _as_float((consensus or {}).get('consensus_confidence'), 0.0)
    route_support = int((consensus or {}).get('route_support_count') or 0)
    if consensus:
        support_bonus = min(0.10, route_support * 0.025)
        confidence_bonus = min(0.10, consensus_conf * 0.10)
        score = base_float + support_bonus + confidence_bonus - penalty
        reason = 'shadow_row_confirmed_by_multi_route_consensus'
        if base >= LOW_RISK_MIN:
            reason = 'low_risk_shadow_row_confirmed_by_multi_route_consensus'
    else:
        score = base_float - penalty - 0.03
        reason = 'shadow_row_without_multi_route_consensus_support'
        if penalty > 0:
            reason = 'shadow_row_penalized_by_route_disagreement_without_consensus'
    return Decimal(str(round(_clamp(score), 3))), reason, consensus_conf, route_support


def build_consensus_weighted_shadow_reconstruction(receipt_json: dict[str, Any]) -> dict[str, Any]:
    shadow = receipt_json.get('metadata', {}).get('shadow_reconstruction_output', {})
    scoring = receipt_json.get('metadata', {}).get('stability_weighted_candidate_scoring', {})
    consensus = receipt_json.get('metadata', {}).get('cross_route_ocr_consensus', {})
    consensus_groups = consensus.get('consensus_groups', []) or []
    disagreements = consensus.get('route_disagreements', []) or []

    source_rows = shadow.get('generated_rows', []) or []
    weighted_rows = []
    rejected_or_penalized = []

    for row in source_rows:
        base = _as_decimal(row.get('reliability_score'), Decimal('0'))
        match = _find_consensus_match(row, consensus_groups)
        penalty, matching_disagreements = _disagreement_penalty(row, disagreements)
        weighted, reason, consensus_conf, route_support = _weighted_score(base, match, penalty)
        output = {
            'product_name': row.get('product_name'),
            'amount': row.get('amount'),
            'amount_text': row.get('amount_text'),
            'amounts': row.get('amounts', []),
            'base_reliability_score': float(base),
            'consensus_confidence': consensus_conf,
            'route_support_count': route_support,
            'route_disagreement_penalty': round(penalty, 3),
            'consensus_weighted_score': float(weighted),
            'risk_level': _risk(weighted),
            'base_risk_level': row.get('risk_level'),
            'weighting_reason': reason,
            'matched_consensus_id': (match or {}).get('consensus_id'),
            'supporting_routes': (match or {}).get('supporting_routes', []),
            'matching_route_disagreements': matching_disagreements,
            'source': 'consensus_weighted_shadow_diagnostic',
            'diagnostic_only': True,
            'reconstruction_applied': False,
        }
        weighted_rows.append(output)
        if output['risk_level'] != 'low' or not match:
            rejected_or_penalized.append(output)

    # Also expose stability candidates that are not shadow rows, for explanation only.
    for candidate in scoring.get('rejected_candidates', []) or []:
        penalty, matching_disagreements = _disagreement_penalty(candidate, disagreements)
        if penalty <= 0:
            continue
        rejected_or_penalized.append({
            'product_name': candidate.get('product_cluster_text'),
            'amount_text': candidate.get('amount_text'),
            'base_reliability_score': candidate.get('reliability_score'),
            'risk_level': candidate.get('risk_level'),
            'weighting_reason': 'non_shadow_candidate_has_route_disagreement',
            'matching_route_disagreements': matching_disagreements,
            'diagnostic_only': True,
            'reconstruction_applied': False,
        })

    return {
        'diagnostic_scope': 'consensus_weighted_shadow_reconstruction',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'strict_shadow_mode': True,
        'weighted_row_count': len(weighted_rows),
        'low_risk_weighted_row_count': sum(1 for row in weighted_rows if row.get('risk_level') == 'low'),
        'penalized_or_non_low_row_count': len(rejected_or_penalized),
        'rules': {
            'source_shadow_rows_unchanged': True,
            'parser_output_changed': False,
            'csv_output_changed': False,
            'max_consensus_bonus': 0.20,
            'max_disagreement_penalty': 0.18,
        },
        'weighted_rows': weighted_rows,
        'penalized_or_non_low_rows': rejected_or_penalized,
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')
    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('consensus_weighted_shadow_reconstruction', {})
    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_consensus_weighted_shadow_reconstruction(payload)
        payload.setdefault('metadata', {})['consensus_weighted_shadow_reconstruction'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['consensus_weighted_shadow_reconstruction'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1
    summary['schema_version'] = 'receipt-ocr-benchmark-v34-consensus-weighted-shadow-reconstruction'
    summary['consensus_weighted_shadow_reconstruction_processed_receipts'] = processed
    summary['consensus_weighted_shadow_reconstruction_skipped_receipts'] = skipped
    summary['consensus_weighted_shadow_reconstruction_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Consensus weighted shadow reconstruction diagnostics added for {processed} receipts; skipped={skipped}')


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
