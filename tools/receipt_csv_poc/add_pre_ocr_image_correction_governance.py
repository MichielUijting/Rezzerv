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


def _risk(value: float, low: float, high: float) -> str:
    if value >= high:
        return 'high'
    if value >= low:
        return 'medium'
    return 'low'


def _best_isolation_variant(receipt_json: dict[str, Any]) -> dict[str, Any]:
    diag = receipt_json.get('metadata', {}).get('document_isolation_enhancement_diagnostics', {})
    best_name = (diag.get('best_variant') or {}).get('variant')
    variants = diag.get('variants', []) or []
    for variant in variants:
        if variant.get('variant') == best_name:
            return variant
    if variants:
        return max(variants, key=lambda item: int(item.get('normalized_group_count_after_isolation') or 0))
    return {}


def _selected_route(receipt_json: dict[str, Any]) -> dict[str, Any]:
    return receipt_json.get('metadata', {}).get('adaptive_ocr_orchestration', {}).get('selected_route', {}) or {}


def _image_quality_findings(receipt_json: dict[str, Any]) -> dict[str, Any]:
    isolation = receipt_json.get('metadata', {}).get('document_isolation_enhancement_diagnostics', {})
    best = _best_isolation_variant(receipt_json)
    route = _selected_route(receipt_json)
    skew = abs(_as_float(isolation.get('estimated_skew_angle')))
    background_noise = _as_float(best.get('background_noise_score'))
    bleed = _as_float(best.get('backside_bleedthrough_score'))
    contrast = _as_float(best.get('local_contrast_score'))
    sharpness = _as_float(best.get('text_sharpness_score'))
    text_scale = _as_float(best.get('normalized_text_scale'))
    iso_conf = _as_float(best.get('isolated_document_confidence'))
    normalized_groups = int(route.get('normalized_group_count') or best.get('normalized_group_count_after_isolation') or 0)
    ocr_regions = int(route.get('ocr_region_count') or best.get('ocr_region_count_after_isolation') or 0)
    shadow_candidates = int(route.get('shadow_candidate_count') or best.get('shadow_candidate_count_after_isolation') or 0)

    perspective_distortion = bool(iso_conf < 0.62 or 'deskew' in str(route.get('preprocessing_variant') or '').lower())
    low_contrast = contrast < 0.38
    low_sharpness = sharpness < 0.32
    small_text = bool(text_scale and text_scale < 0.82)
    likely_good_receipt = bool(ocr_regions >= 35 and normalized_groups >= 6 and background_noise < 0.35 and bleed < 0.35 and sharpness >= 0.40)
    overprocessing_score = 0.0
    if likely_good_receipt:
        overprocessing_score += 0.55
    if contrast >= 0.65 and sharpness >= 0.55:
        overprocessing_score += 0.25
    if bleed < 0.25 and background_noise < 0.25:
        overprocessing_score += 0.20

    return {
        'skew_detected': skew >= 1.8,
        'skew_angle_abs': round(skew, 2),
        'perspective_distortion_detected': perspective_distortion,
        'shadow_risk': _risk(background_noise, 0.32, 0.55),
        'background_noise_score': round(background_noise, 3),
        'bleedthrough_risk': _risk(bleed, 0.32, 0.55),
        'backside_bleedthrough_score': round(bleed, 3),
        'curvature_risk': 'medium' if normalized_groups <= 2 and ocr_regions >= 20 else ('high' if normalized_groups <= 1 and ocr_regions >= 35 else 'low'),
        'low_contrast_detected': low_contrast,
        'local_contrast_score': round(contrast, 3),
        'low_sharpness_detected': low_sharpness,
        'text_sharpness_score': round(sharpness, 3),
        'small_text_detected': small_text,
        'normalized_text_scale': round(text_scale, 3),
        'overprocessing_risk': _risk(overprocessing_score, 0.45, 0.70),
        'minimal_processing_recommended': likely_good_receipt,
        'ocr_region_count_signal': ocr_regions,
        'normalized_group_count_signal': normalized_groups,
        'shadow_candidate_count_signal': shadow_candidates,
    }


def _recommendations(findings: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    recommended = []
    blocked = []

    def add_rec(correction: str, reason: str, risk: str = 'low') -> None:
        recommended.append({
            'correction': correction,
            'recommendation': 'apply_diagnostic_only',
            'reason': reason,
            'regression_risk': risk,
            'diagnostic_only': True,
            'parser_output_changed': False,
            'csv_output_changed': False,
        })

    def add_block(correction: str, reason: str, risk: str = 'high') -> None:
        blocked.append({
            'correction': correction,
            'recommendation': 'block_for_now',
            'reason': reason,
            'regression_risk': risk,
            'diagnostic_only': True,
            'parser_output_changed': False,
            'csv_output_changed': False,
        })

    if findings.get('minimal_processing_recommended'):
        add_rec('minimal_processing', 'receipt_already_has_stable_ocr_structure', 'low')
        add_block('heavy_thresholding', 'high_regression_risk_on_good_receipts', 'high')
        add_block('aggressive_sharpen', 'can_introduce_noise_on_good_receipts', 'medium')
        add_block('dewarp', 'no_curvature_signal_strong_enough', 'medium')
        return recommended, blocked

    if findings.get('skew_detected'):
        add_rec('deskew', 'skew_above_safe_threshold', 'low')
    else:
        add_block('deskew', 'skew_below_threshold', 'medium')

    if findings.get('perspective_distortion_detected'):
        add_rec('perspective_correction', 'document_geometry_instability_detected', 'medium')
        add_rec('document_isolation_crop', 'document_box_or_route_confidence_indicates_isolation_needed', 'low')
    else:
        add_block('perspective_correction', 'no_clear_perspective_signal', 'medium')

    if findings.get('shadow_risk') in {'medium', 'high'}:
        add_rec('local_illumination_correction', 'background_noise_or_shadow_risk_detected', 'low')
        add_rec('shadow_suppression', 'shadow_risk_not_low', 'medium')

    if findings.get('bleedthrough_risk') in {'medium', 'high'}:
        add_rec('bleedthrough_suppression', 'backside_bleedthrough_risk_detected', 'medium')
    else:
        add_block('bleedthrough_suppression', 'bleedthrough_risk_low_so_correction_may_remove_real_text', 'medium')

    if findings.get('low_contrast_detected'):
        add_rec('local_contrast_enhancement', 'local_contrast_below_threshold', 'low')
        add_rec('adaptive_thresholding', 'low_contrast_requires_threshold_experiment', 'medium')
    elif findings.get('overprocessing_risk') == 'high':
        add_block('adaptive_thresholding', 'high_overprocessing_risk', 'high')
    else:
        add_block('heavy_thresholding', 'contrast_not_low_enough_for_heavy_thresholding', 'medium')

    if findings.get('low_sharpness_detected'):
        add_rec('local_sharpen', 'text_sharpness_below_threshold', 'medium')
    else:
        add_block('aggressive_sharpen', 'text_sharpness_already_sufficient_or_noise_risk', 'medium')

    if findings.get('small_text_detected'):
        add_rec('scale_up', 'normalized_text_scale_below_target', 'low')
    else:
        add_block('scale_up', 'text_scale_already_sufficient_or_unknown', 'medium')

    if findings.get('curvature_risk') in {'medium', 'high'}:
        add_rec('curvature_dewarp_candidate_detection', 'many_ocr_regions_but_few_structural_groups', 'medium')
    else:
        add_block('dewarp', 'curvature_risk_low', 'medium')

    return recommended, blocked


def _safe_route(findings: dict[str, Any], recommended: list[dict[str, Any]]) -> dict[str, Any]:
    if findings.get('minimal_processing_recommended'):
        return {
            'route_name': 'minimal_processing',
            'safe_for_future_testing': True,
            'route_reason': 'receipt_already_stable_prevent_overprocessing_regression',
        }
    corrections = [item['correction'] for item in recommended if item.get('correction') != 'minimal_processing']
    conservative = [c for c in corrections if c in {'document_isolation_crop', 'deskew', 'local_contrast_enhancement', 'scale_up'}]
    if not conservative:
        conservative = ['existing_best_q5_route_only']
    route_name = '_'.join(conservative[:4])
    risk_reasons = []
    if findings.get('shadow_risk') in {'medium', 'high'}:
        risk_reasons.append('shadow_or_background_noise')
    if findings.get('bleedthrough_risk') in {'medium', 'high'}:
        risk_reasons.append('bleedthrough')
    if findings.get('curvature_risk') in {'medium', 'high'}:
        risk_reasons.append('curvature_candidate')
    if not risk_reasons:
        risk_reasons.append('improves_structural_groups_without_increasing_noise')
    return {
        'route_name': route_name,
        'safe_for_future_testing': True,
        'route_reason': ','.join(risk_reasons),
    }


def build_pre_ocr_image_correction_governance(receipt_json: dict[str, Any]) -> dict[str, Any]:
    findings = _image_quality_findings(receipt_json)
    recommended, blocked = _recommendations(findings)
    safe_route = _safe_route(findings, recommended)
    return {
        'diagnostic_scope': 'pre_ocr_image_correction_governance',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'parser_output_changed': False,
        'csv_output_changed': False,
        'image_quality_findings': findings,
        'recommended_corrections': recommended,
        'blocked_corrections': blocked,
        'safe_route': safe_route,
        'rules': {
            'governance_only': True,
            'preprocessing_applied_to_parser_input': False,
            'heavy_preprocessing_requires_explicit_image_quality_signal': True,
            'minimal_processing_recommended_for_stable_receipts': True,
        },
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')
    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('pre_ocr_image_correction_governance', {})
    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            # Allow app/screenshot receipts that do not pass _should_run_for_image to still receive minimal governance if JSON exists.
            if not json_path.exists():
                skipped += 1
                continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_pre_ocr_image_correction_governance(payload)
        payload.setdefault('metadata', {})['pre_ocr_image_correction_governance'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['pre_ocr_image_correction_governance'][payload.get('metadata', {}).get('source_file', f'{target}.json')] = diagnostics
        processed += 1
    summary['schema_version'] = 'receipt-ocr-benchmark-v37-pre-ocr-image-correction-governance'
    summary['pre_ocr_image_correction_governance_processed_receipts'] = processed
    summary['pre_ocr_image_correction_governance_skipped_receipts'] = skipped
    summary['pre_ocr_image_correction_governance_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Pre-OCR image correction governance diagnostics added for {processed} receipts; skipped={skipped}')


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
