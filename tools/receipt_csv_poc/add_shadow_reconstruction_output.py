from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from add_amount_region_zone_diagnostics import _image_by_stem, _should_run_for_image

DEFAULT_TARGETS = {
    'AH foto 2',
    'Aldi foto 2',
    'Plus foto 2',
    'plus foto 1',
}
LOW_RISK_LEVEL = 'low'
MIN_LOW_RISK_SCORE = Decimal('0.82')


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


def _to_decimal(value: object, default: Decimal = Decimal('0')) -> Decimal:
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _amount_from_candidate(candidate: dict) -> Decimal | None:
    amounts = candidate.get('amounts') or []
    if not amounts:
        amount_text = candidate.get('amount_text')
        if amount_text is None:
            return None
        amounts = [str(amount_text).replace('€', '').replace('EUR', '').strip()]
    value = str(amounts[0]).replace(',', '.').strip()
    try:
        return Decimal(value).quantize(Decimal('0.01'))
    except Exception:
        return None


def _is_low_risk_candidate(candidate: dict) -> tuple[bool, str]:
    risk = str(candidate.get('risk_level') or '').lower()
    score = _to_decimal(candidate.get('reliability_score'))
    if risk != LOW_RISK_LEVEL:
        return False, f'risk_level_not_low:{risk or "missing"}'
    if score < MIN_LOW_RISK_SCORE:
        return False, f'reliability_score_below_low_risk_threshold:{score}'
    amount = _amount_from_candidate(candidate)
    if amount is None:
        return False, 'amount_not_parseable'
    product_name = str(candidate.get('product_cluster_text') or '').strip()
    if not product_name:
        return False, 'product_cluster_text_missing'
    return True, 'low_risk_candidate_passed_shadow_rules'


def build_shadow_reconstruction_output(receipt_json: dict) -> dict[str, object]:
    scoring = receipt_json.get('metadata', {}).get('stability_weighted_candidate_scoring', {})
    generated_rows = []
    rejected_candidates = []

    for candidate in scoring.get('candidates', []):
        accepted, reason = _is_low_risk_candidate(candidate)
        amount = _amount_from_candidate(candidate)
        if accepted and amount is not None:
            generated_rows.append({
                'product_name': str(candidate.get('product_cluster_text') or '').strip(),
                'amount': float(amount),
                'amount_text': candidate.get('amount_text'),
                'amounts': candidate.get('amounts', []),
                'source': 'low_risk_candidate',
                'reliability_score': float(_to_decimal(candidate.get('reliability_score'))),
                'risk_level': candidate.get('risk_level'),
                'variant': candidate.get('variant'),
                'cluster_id': candidate.get('cluster_id'),
                'score_components': candidate.get('score_components', {}),
                'shadow_reason': reason,
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })
        else:
            rejected_candidates.append({
                'product_cluster_text': candidate.get('product_cluster_text'),
                'amount_text': candidate.get('amount_text'),
                'amounts': candidate.get('amounts', []),
                'risk_level': candidate.get('risk_level'),
                'reliability_score': candidate.get('reliability_score'),
                'reject_reason': reason,
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })

    for rejected in scoring.get('rejected_candidates', []):
        rejected_candidates.append({
            'product_cluster_text': rejected.get('product_cluster_text'),
            'amount_text': rejected.get('amount_text'),
            'amounts': rejected.get('amounts', []),
            'risk_level': rejected.get('risk_level'),
            'reliability_score': rejected.get('reliability_score'),
            'reject_reason': rejected.get('reject_reason') or 'source_candidate_rejected_before_shadow_layer',
            'diagnostic_only': True,
            'reconstruction_applied': False,
        })

    return {
        'diagnostic_scope': 'strict_shadow_reconstruction_output_from_low_risk_candidates',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'strict_shadow_mode': True,
        'generated_row_count': len(generated_rows),
        'rejected_candidate_count': len(rejected_candidates),
        'rules': {
            'allowed_source': 'stability_weighted_candidate_scoring.candidates',
            'required_risk_level': LOW_RISK_LEVEL,
            'min_reliability_score': float(MIN_LOW_RISK_SCORE),
            'csv_output_changed': False,
            'parser_output_changed': False,
        },
        'generated_rows': generated_rows,
        'rejected_candidates': rejected_candidates,
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('shadow_reconstruction_output', {})

    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_shadow_reconstruction_output(payload)
        payload.setdefault('metadata', {})['shadow_reconstruction_output'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['shadow_reconstruction_output'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1

    summary['schema_version'] = 'receipt-ocr-benchmark-v27-shadow-reconstruction-output'
    summary['shadow_reconstruction_output_processed_receipts'] = processed
    summary['shadow_reconstruction_output_skipped_receipts'] = skipped
    summary['shadow_reconstruction_output_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Shadow reconstruction output added for {processed} receipts; skipped={skipped}')


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
