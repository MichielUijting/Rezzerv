from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from add_amount_region_zone_diagnostics import _image_by_stem, _should_run_for_image

DEFAULT_TARGETS = {
    'AH foto 2',
    'AH foto 3',
    'Aldi foto 2',
    'Plus foto 2',
    'plus foto 1',
    'Jumbo App 1',
    'Lidl App 1',
    'Lidl App 2',
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


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _best_variant(receipt_json: dict[str, Any], route_name: str) -> dict[str, Any]:
    isolation = receipt_json.get('metadata', {}).get('document_isolation_enhancement_diagnostics', {})
    variants = isolation.get('variants', []) or []
    route_name_lower = str(route_name or '').lower()
    if not variants:
        return {}
    if 'minimal_processing' in route_name_lower:
        return {}
    scored = []
    for variant in variants:
        name = str(variant.get('variant') or '').lower()
        score = 0
        if 'document_isolation_crop' in route_name_lower and 'isolated' in name:
            score += 2
        if 'deskew' in route_name_lower and 'deskew' in name:
            score += 4
        if 'local_contrast' in route_name_lower and 'contrast' in name:
            score += 4
        if 'scale_up' in route_name_lower and ('scale' in name or 'scaled' in name):
            score += 4
        if 'sharpen' in route_name_lower and 'sharpen' in name:
            score += 4
        if 'threshold' in route_name_lower and 'threshold' in name:
            score += 3
        score += _as_int(variant.get('normalized_group_count_after_isolation'))
        score += _as_int(variant.get('shadow_candidate_count_after_isolation')) * 2
        scored.append((score, variant))
    return max(scored, key=lambda item: item[0])[1] if scored else {}


def _before_metrics(receipt_json: dict[str, Any]) -> dict[str, Any]:
    structural = receipt_json.get('metadata', {}).get('ocr_structural_normalization', {})
    consensus = receipt_json.get('metadata', {}).get('cross_route_ocr_consensus', {})
    readiness = receipt_json.get('metadata', {}).get('parser_safety_gating', {}).get('readiness', {})
    zone = receipt_json.get('metadata', {}).get('amount_region_zone_diagnostics', {}).get('best_article_zone_variant', {})
    orchestration = receipt_json.get('metadata', {}).get('adaptive_ocr_orchestration', {}).get('selected_route', {})
    return {
        'ocr_region_count': _as_int(orchestration.get('ocr_region_count')),
        'article_zone_amount_count': _as_int(zone.get('article_zone_amount_count')),
        'normalized_group_count': _as_int(structural.get('normalized_group_count')),
        'consensus_group_count': _as_int(consensus.get('consensus_group_count')),
        'parser_readiness_score': _as_float(readiness.get('parser_integration_readiness_score')),
    }


def _after_metrics_from_variant(receipt_json: dict[str, Any], variant: dict[str, Any], route_name: str) -> dict[str, Any]:
    before = _before_metrics(receipt_json)
    if not variant or route_name == 'minimal_processing':
        return dict(before)
    # Use measured Q4 variant metrics as simulated post-route metrics. Consensus/readiness remain estimated
    # diagnostically because this release must not replace parser/OCR input.
    after = {
        'ocr_region_count': _as_int(variant.get('ocr_region_count_after_isolation')),
        'article_zone_amount_count': _as_int(variant.get('article_zone_amount_count_after_isolation')),
        'normalized_group_count': _as_int(variant.get('normalized_group_count_after_isolation')),
        'consensus_group_count': max(
            before.get('consensus_group_count', 0),
            min(_as_int(variant.get('normalized_group_count_after_isolation')), _as_int(variant.get('shadow_candidate_count_after_isolation')) + 1),
        ),
        'parser_readiness_score': before.get('parser_readiness_score', 0.0),
    }
    structural_gain = after['normalized_group_count'] - before.get('normalized_group_count', 0)
    consensus_gain = after['consensus_group_count'] - before.get('consensus_group_count', 0)
    amount_gain = after['article_zone_amount_count'] - before.get('article_zone_amount_count', 0)
    readiness_delta = max(-0.20, min(0.35, structural_gain * 0.04 + consensus_gain * 0.06 + amount_gain * 0.03))
    after['parser_readiness_score'] = round(max(0.0, min(1.0, before.get('parser_readiness_score', 0.0) + readiness_delta)), 3)
    return after


def _delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        'ocr_region_delta': _as_int(after.get('ocr_region_count')) - _as_int(before.get('ocr_region_count')),
        'article_zone_amount_delta': _as_int(after.get('article_zone_amount_count')) - _as_int(before.get('article_zone_amount_count')),
        'normalized_group_delta': _as_int(after.get('normalized_group_count')) - _as_int(before.get('normalized_group_count')),
        'consensus_group_delta': _as_int(after.get('consensus_group_count')) - _as_int(before.get('consensus_group_count')),
        'parser_readiness_delta': round(_as_float(after.get('parser_readiness_score')) - _as_float(before.get('parser_readiness_score')), 3),
    }


def _regression_assessment(delta: dict[str, Any], governance: dict[str, Any], route_name: str) -> dict[str, Any]:
    if route_name == 'minimal_processing':
        return {
            'regression_detected': False,
            'regression_risk': 'low',
            'reason': 'minimal_processing_selected_to_prevent_overprocessing',
        }
    negative_structural = _as_int(delta.get('normalized_group_delta')) < 0
    negative_consensus = _as_int(delta.get('consensus_group_delta')) < 0
    readiness_down = _as_float(delta.get('parser_readiness_delta')) < -0.03
    overprocessing = governance.get('image_quality_findings', {}).get('overprocessing_risk') == 'high'
    if negative_structural or negative_consensus or readiness_down:
        return {
            'regression_detected': True,
            'regression_risk': 'high' if overprocessing else 'medium',
            'reason': 'one_or_more_structural_consensus_or_readiness_metrics_decreased',
        }
    if _as_int(delta.get('normalized_group_delta')) > 0 or _as_int(delta.get('consensus_group_delta')) > 0 or _as_float(delta.get('parser_readiness_delta')) > 0:
        return {
            'regression_detected': False,
            'regression_risk': 'low',
            'reason': 'structural_and_consensus_metrics_improved',
        }
    return {
        'regression_detected': False,
        'regression_risk': 'medium' if overprocessing else 'low',
        'reason': 'no_material_metric_change_detected',
    }


def build_adaptive_preprocessing_simulation(receipt_json: dict[str, Any]) -> dict[str, Any]:
    governance = receipt_json.get('metadata', {}).get('pre_ocr_image_correction_governance', {})
    safe_route = governance.get('safe_route', {}) or {}
    route_name = str(safe_route.get('route_name') or 'existing_best_q5_route_only')
    minimal = bool(governance.get('image_quality_findings', {}).get('minimal_processing_recommended')) or route_name == 'minimal_processing'
    variant = {} if minimal else _best_variant(receipt_json, route_name)
    before = _before_metrics(receipt_json)
    after = _after_metrics_from_variant(receipt_json, variant, 'minimal_processing' if minimal else route_name)
    delta = _delta(before, after)
    regression = _regression_assessment(delta, governance, 'minimal_processing' if minimal else route_name)
    safe_for_future = not regression.get('regression_detected') and regression.get('regression_risk') in {'low', 'medium'}
    if regression.get('regression_risk') == 'medium' and _as_float(delta.get('parser_readiness_delta')) <= 0:
        safe_for_future = False
    return {
        'diagnostic_scope': 'safe_adaptive_preprocessing_simulation',
        'diagnostic_only': True,
        'parser_output_changed': False,
        'csv_output_changed': False,
        'simulation_only': True,
        'safe_route_tested': 'minimal_processing' if minimal else route_name,
        'selected_q4_variant_for_simulation': variant.get('variant') if variant else '',
        'before_metrics': before,
        'after_metrics': after,
        'delta': delta,
        'regression_assessment': regression,
        'safe_for_future_preprocessing_integration': safe_for_future,
        'integration_recommendation': 'do_not_integrate_yet' if not safe_for_future else 'eligible_for_limited_future_testing',
        'rules': {
            'source_governance': 'pre_ocr_image_correction_governance.safe_route',
            'simulation_only': True,
            'parser_input_changed': False,
            'csv_output_changed': False,
            'minimal_processing_blocks_heavy_preprocessing': True,
        },
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')
    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('adaptive_preprocessing_simulation', {})
    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            # App/screenshot receipts can still receive minimal-processing simulation when JSON exists.
            if not json_path.exists():
                skipped += 1
                continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_adaptive_preprocessing_simulation(payload)
        payload.setdefault('metadata', {})['adaptive_preprocessing_simulation'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['adaptive_preprocessing_simulation'][payload.get('metadata', {}).get('source_file', f'{target}.json')] = diagnostics
        processed += 1
    summary['schema_version'] = 'receipt-ocr-benchmark-v38-adaptive-preprocessing-simulation'
    summary['adaptive_preprocessing_simulation_processed_receipts'] = processed
    summary['adaptive_preprocessing_simulation_skipped_receipts'] = skipped
    summary['adaptive_preprocessing_simulation_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Adaptive preprocessing simulation diagnostics added for {processed} receipts; skipped={skipped}')


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
