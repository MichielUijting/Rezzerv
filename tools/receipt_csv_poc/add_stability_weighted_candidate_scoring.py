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


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _risk_level(score: float) -> str:
    if score >= 0.82:
        return 'low'
    if score >= 0.62:
        return 'medium'
    return 'high'


def _find_text_stability(receipt_json: dict, cluster_id: str | None, cluster_text: str | None) -> dict:
    stability = receipt_json.get('metadata', {}).get('ocr_text_stability_diagnostics', {})
    for cluster in stability.get('clusters', []):
        if cluster_id and cluster.get('cluster_id') == cluster_id:
            return cluster
    normalized_target = ' '.join(str(cluster_text or '').lower().split())
    for cluster in stability.get('clusters', []):
        normalized = ' '.join(' '.join(cluster.get('cluster_text_lines', [])).lower().split())
        if normalized_target and normalized == normalized_target:
            return cluster
    return {}


def _component_alignment(source: dict) -> float:
    raw_score = _as_float(source.get('flexible_alignment_score'), 0.0) / 100.0
    validation = str(source.get('flexible_alignment_validation') or '')
    if validation == 'strict_same_line_candidate':
        raw_score = max(raw_score, 0.90)
    elif validation == 'relaxed_visual_alignment_candidate':
        raw_score = max(raw_score, 0.72)
    return round(_clamp(raw_score), 3)


def _component_geometry(source: dict) -> float:
    baseline = _as_float(source.get('baseline_distance_pixels'), 999.0)
    overlap = _as_float(source.get('vertical_overlap_percentage'), 0.0) / 100.0
    baseline_component = 1.0 - _clamp(baseline / 80.0)
    geometry = (baseline_component * 0.55) + (_clamp(overlap) * 0.45)
    return round(_clamp(geometry), 3)


def _component_ocr_confidence(source: dict, stability_cluster: dict) -> float:
    amount_conf = _as_float(source.get('amount_mean_confidence'), 0.0) / 100.0
    cluster_conf = _as_float(source.get('cluster_confidence'), _as_float(stability_cluster.get('cluster_confidence'), 50.0)) / 100.0
    if amount_conf <= 0:
        amount_conf = 0.50
    if cluster_conf <= 0:
        cluster_conf = 0.50
    return round(_clamp((amount_conf * 0.55) + (cluster_conf * 0.45)), 3)


def _component_text_stability(stability_cluster: dict) -> float:
    text_stability = _as_float(stability_cluster.get('text_stability_score'), 0.0)
    multi_pass = _as_float(stability_cluster.get('multi_pass_ocr_text_similarity'), 0.0)
    confidence_variance = _as_float(stability_cluster.get('confidence_variance'), 0.0)
    pseudo_noise = _as_float(stability_cluster.get('pseudo_amount_noise_count'), 0.0)
    variance_component = 1.0 - _clamp(confidence_variance / 500.0)
    noise_component = 1.0 - _clamp(pseudo_noise / 3.0)
    if text_stability <= 0 and not stability_cluster:
        return 0.45
    score = (text_stability * 0.45) + (multi_pass * 0.25) + (variance_component * 0.15) + (noise_component * 0.15)
    return round(_clamp(score), 3)


def _score_candidate(candidate: dict, receipt_json: dict) -> dict:
    source = candidate.get('source_validations', {}) or {}
    cluster_id = candidate.get('cluster_id')
    cluster_text = candidate.get('product_cluster_text')
    stability_cluster = _find_text_stability(receipt_json, cluster_id, cluster_text)

    components = {
        'alignment': _component_alignment(source),
        'text_stability': _component_text_stability(stability_cluster),
        'ocr_confidence': _component_ocr_confidence(source, stability_cluster),
        'geometry': _component_geometry(source),
    }
    reliability = (
        components['alignment'] * 0.30
        + components['text_stability'] * 0.30
        + components['ocr_confidence'] * 0.20
        + components['geometry'] * 0.20
    )
    reliability = round(_clamp(reliability), 3)
    return {
        'product_cluster_text': candidate.get('product_cluster_text'),
        'cluster_id': candidate.get('cluster_id'),
        'cluster_text_lines': candidate.get('cluster_text_lines', []),
        'amount_text': candidate.get('amount_text'),
        'amounts': candidate.get('amounts', []),
        'variant': candidate.get('variant'),
        'reliability_score': reliability,
        'risk_level': _risk_level(reliability),
        'score_components': components,
        'source_candidate_reason': candidate.get('candidate_reason'),
        'source_confidence_score': candidate.get('confidence_score'),
        'source_validations': source,
        'stability_inputs': {
            'text_stability_score': stability_cluster.get('text_stability_score'),
            'multi_pass_ocr_text_similarity': stability_cluster.get('multi_pass_ocr_text_similarity'),
            'confidence_variance': stability_cluster.get('confidence_variance'),
            'pseudo_amount_noise_count': stability_cluster.get('pseudo_amount_noise_count'),
        },
        'diagnostic_only': True,
        'reconstruction_applied': False,
    }


def _score_rejected_candidate(rejected: dict, receipt_json: dict) -> dict:
    cluster_text = rejected.get('product_name_text')
    stability_cluster = _find_text_stability(receipt_json, None, cluster_text)
    source = {
        'flexible_alignment_score': rejected.get('flexible_alignment_score'),
        'flexible_alignment_validation': rejected.get('flexible_alignment_validation'),
        'baseline_distance_pixels': rejected.get('baseline_distance_pixels'),
        'vertical_overlap_percentage': rejected.get('vertical_overlap_percentage'),
        'amount_mean_confidence': rejected.get('amount_mean_confidence'),
    }
    components = {
        'alignment': _component_alignment(source),
        'text_stability': _component_text_stability(stability_cluster),
        'ocr_confidence': _component_ocr_confidence(source, stability_cluster),
        'geometry': _component_geometry(source),
    }
    reliability = round(_clamp(components['alignment'] * 0.25 + components['text_stability'] * 0.25 + components['ocr_confidence'] * 0.15 + components['geometry'] * 0.15), 3)
    return {
        'product_cluster_text': rejected.get('product_name_text'),
        'amount_text': rejected.get('amount_text'),
        'amounts': rejected.get('amounts', []),
        'variant': rejected.get('variant'),
        'reliability_score': reliability,
        'risk_level': _risk_level(reliability),
        'reject_reason': rejected.get('reject_reason'),
        'score_components': components,
        'diagnostic_only': True,
        'reconstruction_applied': False,
    }


def build_stability_weighted_candidate_scoring(receipt_json: dict) -> dict[str, object]:
    reconstruction = receipt_json.get('metadata', {}).get('diagnostic_reconstruction_candidates', {})
    candidates = [_score_candidate(candidate, receipt_json) for candidate in reconstruction.get('candidates', [])]
    rejected = [_score_rejected_candidate(candidate, receipt_json) for candidate in reconstruction.get('rejected_candidates', [])]

    low = sum(1 for candidate in candidates if candidate.get('risk_level') == 'low')
    medium = sum(1 for candidate in candidates if candidate.get('risk_level') == 'medium')
    high = sum(1 for candidate in candidates if candidate.get('risk_level') == 'high')
    return {
        'diagnostic_scope': 'stability_weighted_reconstruction_candidate_scoring',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'candidate_count': len(candidates),
        'rejected_candidate_count': len(rejected),
        'risk_counts': {'low': low, 'medium': medium, 'high': high},
        'weights': {
            'alignment': 0.30,
            'text_stability': 0.30,
            'ocr_confidence': 0.20,
            'geometry': 0.20,
        },
        'risk_thresholds': {
            'low_min': 0.82,
            'medium_min': 0.62,
            'high_below': 0.62,
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
    summary.setdefault('stability_weighted_candidate_scoring', {})

    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_stability_weighted_candidate_scoring(payload)
        payload.setdefault('metadata', {})['stability_weighted_candidate_scoring'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['stability_weighted_candidate_scoring'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1

    summary['schema_version'] = 'receipt-ocr-benchmark-v26-stability-weighted-candidate-scoring'
    summary['stability_weighted_candidate_scoring_processed_receipts'] = processed
    summary['stability_weighted_candidate_scoring_skipped_receipts'] = skipped
    summary['stability_weighted_candidate_scoring_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Stability weighted candidate scoring added for {processed} receipts; skipped={skipped}')


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
