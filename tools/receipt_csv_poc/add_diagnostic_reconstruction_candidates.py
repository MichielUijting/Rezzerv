from __future__ import annotations

import argparse
import json
from pathlib import Path

from add_amount_region_zone_diagnostics import _image_by_stem, _should_run_for_image

DEFAULT_TARGETS = {
    'AH foto 2',
    'Aldi foto 2',
    'Plus foto 2',
    'plus foto 1',
}

MIN_ALIGNMENT_SCORE = 70
MIN_VERTICAL_OVERLAP_PERCENTAGE = 12
MAX_BASELINE_DISTANCE_PIXELS = 58
MIN_AMOUNT_CONFIDENCE = 35
MIN_CLUSTER_CONFIDENCE = 0


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
    parts = raw.parts
    prefix_parts = prefix.parts
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


def _cluster_key(text: str, amount_text: str, variant: str) -> str:
    return f'{variant}|{text}|{amount_text}'


def _cluster_candidates(receipt_json: dict) -> dict[str, dict]:
    clusters_diag = receipt_json.get('metadata', {}).get('ocr_product_clusters', {})
    candidates: dict[str, dict] = {}
    for cluster in clusters_diag.get('clusters', []):
        cluster_text = ' '.join(cluster.get('cluster_text_lines', []))
        for linked in cluster.get('linked_amount_candidates', []):
            key = _cluster_key(cluster_text, str(linked.get('amount_text') or ''), str(linked.get('variant') or ''))
            candidates[key] = {
                'product_cluster_text': cluster_text,
                'cluster_id': cluster.get('cluster_id'),
                'cluster_box': cluster.get('cluster_box'),
                'cluster_text_lines': cluster.get('cluster_text_lines', []),
                'cluster_confidence': cluster.get('cluster_confidence'),
                'amount_text': linked.get('amount_text'),
                'amounts': linked.get('amounts', []),
                'amount_box': linked.get('amount_box'),
                'amount_mean_confidence': linked.get('amount_mean_confidence'),
                'variant': linked.get('variant'),
                'cluster_validation': linked.get('validation'),
                'cluster_reason': linked.get('reason'),
                'cluster_baseline_distance_pixels': linked.get('baseline_distance_pixels'),
            }
    return candidates


def _flexible_candidates(receipt_json: dict) -> list[dict]:
    flex_diag = receipt_json.get('metadata', {}).get('flexible_alignment_validation', {})
    results: list[dict] = []
    for variant in flex_diag.get('variants', []):
        variant_name = str(variant.get('variant') or '')
        for pair in variant.get('validated_pairs', []):
            validation = pair.get('validation')
            if validation not in {'strict_same_line_candidate', 'relaxed_visual_alignment_candidate'}:
                continue
            enriched = dict(pair)
            enriched['variant'] = variant_name
            results.append(enriched)
    return results


def _confidence_value(value: object) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


def _combined_confidence_score(flex_pair: dict, cluster_match: dict) -> float:
    alignment_score = min(100.0, float(flex_pair.get('flexible_alignment_score') or 0)) / 100.0
    amount_confidence = max(_confidence_value(flex_pair.get('amount_mean_confidence')), _confidence_value(cluster_match.get('amount_mean_confidence'))) / 100.0
    cluster_confidence = _confidence_value(cluster_match.get('cluster_confidence')) / 100.0
    if cluster_confidence <= 0:
        cluster_confidence = 0.5
    overlap_score = min(100.0, float(flex_pair.get('vertical_overlap_percentage') or 0)) / 100.0
    score = (alignment_score * 0.40) + (amount_confidence * 0.25) + (cluster_confidence * 0.20) + (overlap_score * 0.15)
    return round(max(0.0, min(1.0, score)), 3)


def _validate_strict_candidate(flex_pair: dict, cluster_match: dict | None) -> tuple[bool, str]:
    if cluster_match is None:
        return False, 'missing_cluster_alignment_candidate'
    if cluster_match.get('cluster_validation') != 'cluster_alignment_candidate':
        return False, 'cluster_validation_not_candidate'
    if flex_pair.get('validation') not in {'strict_same_line_candidate', 'relaxed_visual_alignment_candidate'}:
        return False, 'flexible_alignment_not_candidate'
    if int(flex_pair.get('baseline_distance_pixels') or 999999) > MAX_BASELINE_DISTANCE_PIXELS:
        return False, 'baseline_distance_exceeds_strict_limit'
    if int(flex_pair.get('vertical_overlap_percentage') or 0) < MIN_VERTICAL_OVERLAP_PERCENTAGE:
        return False, 'vertical_overlap_below_strict_limit'
    if int(flex_pair.get('flexible_alignment_score') or 0) < MIN_ALIGNMENT_SCORE:
        return False, 'alignment_score_below_strict_limit'
    amount_confidence = max(_confidence_value(flex_pair.get('amount_mean_confidence')), _confidence_value(cluster_match.get('amount_mean_confidence')))
    if amount_confidence < MIN_AMOUNT_CONFIDENCE:
        return False, 'amount_confidence_below_strict_limit'
    cluster_confidence = _confidence_value(cluster_match.get('cluster_confidence'))
    if cluster_confidence and cluster_confidence < MIN_CLUSTER_CONFIDENCE:
        return False, 'cluster_confidence_below_strict_limit'
    return True, 'article_zone_cluster_alignment_relaxed_match'


def build_diagnostic_reconstruction_candidates(receipt_json: dict) -> dict[str, object]:
    clusters = _cluster_candidates(receipt_json)
    flex_pairs = _flexible_candidates(receipt_json)
    candidates = []
    rejected = []

    for pair in flex_pairs:
        product_text = str(pair.get('product_name_text') or pair.get('product_name_raw_line') or '')
        amount_text = str(pair.get('amount_text') or '')
        variant = str(pair.get('variant') or '')
        exact_key = _cluster_key(product_text, amount_text, variant)
        cluster_match = clusters.get(exact_key)

        if cluster_match is None:
            # Conservative fallback: same amount and variant, cluster text contains product text or vice versa.
            normalized_product = product_text.lower().strip()
            for key, possible in clusters.items():
                if possible.get('variant') != variant or str(possible.get('amount_text') or '') != amount_text:
                    continue
                cluster_text = str(possible.get('product_cluster_text') or '').lower().strip()
                if normalized_product and (normalized_product in cluster_text or cluster_text in normalized_product):
                    cluster_match = possible
                    break

        accepted, reason = _validate_strict_candidate(pair, cluster_match)
        if accepted and cluster_match:
            candidates.append({
                'product_cluster_text': cluster_match.get('product_cluster_text'),
                'cluster_id': cluster_match.get('cluster_id'),
                'cluster_text_lines': cluster_match.get('cluster_text_lines', []),
                'cluster_box': cluster_match.get('cluster_box'),
                'amount_text': amount_text,
                'amounts': pair.get('amounts', []),
                'amount_box': pair.get('amount_box'),
                'variant': variant,
                'confidence_score': _combined_confidence_score(pair, cluster_match),
                'candidate_reason': reason,
                'source_validations': {
                    'article_zone': True,
                    'cluster_alignment_candidate': True,
                    'flexible_alignment_validation': pair.get('validation'),
                    'baseline_distance_pixels': pair.get('baseline_distance_pixels'),
                    'vertical_overlap_percentage': pair.get('vertical_overlap_percentage'),
                    'flexible_alignment_score': pair.get('flexible_alignment_score'),
                    'amount_mean_confidence': pair.get('amount_mean_confidence'),
                    'cluster_confidence': cluster_match.get('cluster_confidence'),
                },
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })
        else:
            rejected.append({
                'product_name_text': product_text,
                'amount_text': amount_text,
                'amounts': pair.get('amounts', []),
                'variant': variant,
                'reject_reason': reason,
                'flexible_alignment_validation': pair.get('validation'),
                'baseline_distance_pixels': pair.get('baseline_distance_pixels'),
                'vertical_overlap_percentage': pair.get('vertical_overlap_percentage'),
                'flexible_alignment_score': pair.get('flexible_alignment_score'),
                'has_cluster_match': cluster_match is not None,
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })

    return {
        'diagnostic_scope': 'strict_diagnostic_reconstruction_candidate_generation',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'strict_mode': True,
        'candidate_count': len(candidates),
        'rejected_candidate_count': len(rejected),
        'limits': {
            'min_alignment_score': MIN_ALIGNMENT_SCORE,
            'min_vertical_overlap_percentage': MIN_VERTICAL_OVERLAP_PERCENTAGE,
            'max_baseline_distance_pixels': MAX_BASELINE_DISTANCE_PIXELS,
            'min_amount_confidence': MIN_AMOUNT_CONFIDENCE,
            'min_cluster_confidence': MIN_CLUSTER_CONFIDENCE,
        },
        'candidates': candidates,
        'rejected_candidates': rejected,
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('diagnostic_reconstruction_candidates', {})

    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_diagnostic_reconstruction_candidates(payload)
        payload.setdefault('metadata', {})['diagnostic_reconstruction_candidates'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['diagnostic_reconstruction_candidates'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1

    summary['schema_version'] = 'receipt-ocr-benchmark-v24-diagnostic-reconstruction-candidates'
    summary['diagnostic_reconstruction_candidates_processed_receipts'] = processed
    summary['diagnostic_reconstruction_candidates_skipped_receipts'] = skipped
    summary['diagnostic_reconstruction_candidates_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Diagnostic reconstruction candidates added for {processed} receipts; skipped={skipped}')


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
