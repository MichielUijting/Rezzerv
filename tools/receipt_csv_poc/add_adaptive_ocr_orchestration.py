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
}
DEFAULT_OCR_CONFIG = '--psm 11 nld+eng'


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


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _quality_score(variant: dict[str, Any]) -> float:
    contrast = _as_float(variant.get('local_contrast_score'))
    sharpness = _as_float(variant.get('text_sharpness_score'))
    background_noise = _as_float(variant.get('background_noise_score'))
    bleed = _as_float(variant.get('backside_bleedthrough_score'))
    text_scale = _as_float(variant.get('normalized_text_scale'))
    text_scale_score = 1.0 - min(1.0, abs(text_scale - 1.0) / 1.5) if text_scale else 0.35
    score = (
        contrast * 0.25
        + sharpness * 0.25
        + (1.0 - _clamp(background_noise)) * 0.20
        + (1.0 - _clamp(bleed)) * 0.20
        + text_scale_score * 0.10
    )
    return round(_clamp(score), 3)


def _normalize_count(value: Any, divisor: float) -> float:
    return _clamp(_as_float(value) / divisor)


def _route_score(route: dict[str, Any]) -> float:
    structural = _normalize_count(route.get('normalized_group_count'), 8.0)
    shadow = _normalize_count(route.get('shadow_candidate_count'), 4.0)
    article_amounts = _normalize_count(route.get('article_zone_amount_count'), 6.0)
    ocr_regions = _normalize_count(route.get('ocr_region_count'), 80.0)
    image_quality = _as_float(route.get('image_quality_score'))
    score = (
        structural * 0.30
        + shadow * 0.25
        + article_amounts * 0.20
        + image_quality * 0.15
        + ocr_regions * 0.10
    )
    return round(_clamp(score), 3)


def _best_ocr_config_for_variant(receipt_json: dict[str, Any], variant_name: str) -> dict[str, Any]:
    engine = receipt_json.get('metadata', {}).get('ocr_engine_comparison', {})
    best_overall = engine.get('best_overall_config') or {}
    for variant in engine.get('variants', []) or []:
        if variant.get('variant') == variant_name:
            return variant.get('best_config') or best_overall or {}
    return best_overall or {}


def _build_routes_from_isolation(receipt_json: dict[str, Any]) -> list[dict[str, Any]]:
    isolation = receipt_json.get('metadata', {}).get('document_isolation_enhancement_diagnostics', {})
    routes = []
    for variant in isolation.get('variants', []) or []:
        variant_name = str(variant.get('variant') or '')
        best_ocr = _best_ocr_config_for_variant(receipt_json, variant_name)
        config = best_ocr.get('config') or DEFAULT_OCR_CONFIG
        route = {
            'preprocessing_variant': variant_name,
            'ocr_config': config,
            'ocr_config_label': best_ocr.get('config_label') or 'default_psm11_nld_eng',
            'ocr_region_count': int(variant.get('ocr_region_count_after_isolation') or 0),
            'article_zone_amount_count': int(variant.get('article_zone_amount_count_after_isolation') or 0),
            'normalized_group_count': int(variant.get('normalized_group_count_after_isolation') or 0),
            'shadow_candidate_count': int(variant.get('shadow_candidate_count_after_isolation') or 0),
            'image_quality_score': _quality_score(variant),
            'source_metrics': {
                'isolated_document_confidence': variant.get('isolated_document_confidence'),
                'background_noise_score': variant.get('background_noise_score'),
                'backside_bleedthrough_score': variant.get('backside_bleedthrough_score'),
                'local_contrast_score': variant.get('local_contrast_score'),
                'text_sharpness_score': variant.get('text_sharpness_score'),
                'normalized_text_scale': variant.get('normalized_text_scale'),
            },
            'diagnostic_only': True,
            'reconstruction_applied': False,
        }
        route['route_score'] = _route_score(route)
        routes.append(route)
    return routes


def _fallback_route(receipt_json: dict[str, Any]) -> dict[str, Any]:
    structural = receipt_json.get('metadata', {}).get('ocr_structural_normalization', {})
    shadow = receipt_json.get('metadata', {}).get('shadow_reconstruction_output', {})
    zone = receipt_json.get('metadata', {}).get('amount_region_zone_diagnostics', {})
    best_zone = zone.get('best_article_zone_variant') or {}
    route = {
        'preprocessing_variant': 'existing_latest_run_outputs',
        'ocr_config': DEFAULT_OCR_CONFIG,
        'ocr_config_label': 'fallback_existing_outputs',
        'ocr_region_count': 0,
        'article_zone_amount_count': int(best_zone.get('article_zone_amount_count') or 0),
        'normalized_group_count': int(structural.get('normalized_group_count') or 0),
        'shadow_candidate_count': int(shadow.get('generated_row_count') or 0),
        'image_quality_score': 0.50,
        'source_metrics': {},
        'diagnostic_only': True,
        'reconstruction_applied': False,
    }
    route['route_score'] = _route_score(route)
    return route


def build_adaptive_ocr_orchestration(receipt_json: dict[str, Any]) -> dict[str, Any]:
    routes = _build_routes_from_isolation(receipt_json)
    if not routes:
        routes = [_fallback_route(receipt_json)]
    routes = sorted(routes, key=lambda item: item.get('route_score', 0), reverse=True)
    selected = routes[0]
    selection_reason = 'highest_weighted_structural_and_shadow_score'
    if selected.get('shadow_candidate_count', 0) == 0 and selected.get('normalized_group_count', 0) > 0:
        selection_reason = 'highest_weighted_structural_score_no_shadow_candidates'
    if selected.get('normalized_group_count', 0) == 0:
        selection_reason = 'best_available_image_quality_and_ocr_signal_no_structural_groups'
    return {
        'diagnostic_scope': 'adaptive_ocr_route_selection_from_existing_diagnostics',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'selected_route': {
            'preprocessing_variant': selected.get('preprocessing_variant'),
            'ocr_config': selected.get('ocr_config'),
            'ocr_config_label': selected.get('ocr_config_label'),
            'selection_reason': selection_reason,
            'route_score': selected.get('route_score'),
            'image_quality_score': selected.get('image_quality_score'),
            'ocr_region_count': selected.get('ocr_region_count'),
            'article_zone_amount_count': selected.get('article_zone_amount_count'),
            'normalized_group_count': selected.get('normalized_group_count'),
            'shadow_candidate_count': selected.get('shadow_candidate_count'),
        },
        'weights': {
            'normalized_group_count': 0.30,
            'shadow_candidate_count': 0.25,
            'article_zone_amount_count': 0.20,
            'image_quality_score': 0.15,
            'ocr_region_count': 0.10,
        },
        'route_candidate_count': len(routes),
        'route_candidates': routes,
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')
    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('adaptive_ocr_orchestration', {})
    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_adaptive_ocr_orchestration(payload)
        payload.setdefault('metadata', {})['adaptive_ocr_orchestration'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['adaptive_ocr_orchestration'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1
    summary['schema_version'] = 'receipt-ocr-benchmark-v32-adaptive-ocr-orchestration'
    summary['adaptive_ocr_orchestration_processed_receipts'] = processed
    summary['adaptive_ocr_orchestration_skipped_receipts'] = skipped
    summary['adaptive_ocr_orchestration_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Adaptive OCR orchestration diagnostics added for {processed} receipts; skipped={skipped}')


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
