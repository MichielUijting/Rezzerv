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
ZONES = [
    'header_zone',
    'article_product_zone',
    'article_amount_zone',
    'total_zone',
    'payment_zone',
    'footer_noise_zone',
]


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


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _risk(value: float, medium: float, high: float) -> str:
    if value >= high:
        return 'high'
    if value >= medium:
        return 'medium'
    return 'low'


def _base_quality(receipt_json: dict[str, Any]) -> dict[str, float]:
    governance = receipt_json.get('metadata', {}).get('pre_ocr_image_correction_governance', {})
    findings = governance.get('image_quality_findings', {}) or {}
    best_variant = _best_variant(receipt_json)
    return {
        'contrast': _as_float(findings.get('local_contrast_score'), _as_float(best_variant.get('local_contrast_score'), 0.50)),
        'sharpness': _as_float(findings.get('text_sharpness_score'), _as_float(best_variant.get('text_sharpness_score'), 0.50)),
        'shadow': _as_float(findings.get('background_noise_score'), _as_float(best_variant.get('background_noise_score'), 0.30)),
        'bleed': _as_float(findings.get('backside_bleedthrough_score'), _as_float(best_variant.get('backside_bleedthrough_score'), 0.25)),
        'scale': _as_float(findings.get('normalized_text_scale'), _as_float(best_variant.get('normalized_text_scale'), 1.00)),
    }


def _best_variant(receipt_json: dict[str, Any]) -> dict[str, Any]:
    isolation = receipt_json.get('metadata', {}).get('document_isolation_enhancement_diagnostics', {})
    best_name = (isolation.get('best_variant') or {}).get('variant')
    for variant in isolation.get('variants', []) or []:
        if variant.get('variant') == best_name:
            return variant
    variants = isolation.get('variants', []) or []
    return variants[0] if variants else {}


def _zone_modifier(zone: str) -> dict[str, float]:
    # Generic geometric priors, no store-specific assumptions.
    if zone == 'header_zone':
        return {'contrast': 0.03, 'sharpness': 0.02, 'shadow': -0.02, 'bleed': 0.00, 'scale': 0.02}
    if zone == 'article_product_zone':
        return {'contrast': -0.04, 'sharpness': -0.02, 'shadow': 0.05, 'bleed': 0.02, 'scale': -0.04}
    if zone == 'article_amount_zone':
        return {'contrast': -0.06, 'sharpness': -0.05, 'shadow': 0.04, 'bleed': 0.03, 'scale': -0.10}
    if zone == 'total_zone':
        return {'contrast': 0.00, 'sharpness': 0.00, 'shadow': 0.02, 'bleed': 0.03, 'scale': 0.00}
    if zone == 'payment_zone':
        return {'contrast': -0.01, 'sharpness': -0.01, 'shadow': 0.08, 'bleed': 0.06, 'scale': -0.02}
    return {'contrast': -0.04, 'sharpness': -0.03, 'shadow': 0.12, 'bleed': 0.10, 'scale': -0.03}


def _zone_quality(base: dict[str, float], zone: str) -> dict[str, float]:
    mod = _zone_modifier(zone)
    scale = base['scale'] + mod['scale']
    text_scale_score = 1.0 - min(1.0, abs(scale - 1.0) / 1.6) if scale else 0.35
    return {
        'contrast_score': round(_clamp(base['contrast'] + mod['contrast']), 3),
        'sharpness_score': round(_clamp(base['sharpness'] + mod['sharpness']), 3),
        'shadow_score': round(_clamp(base['shadow'] + mod['shadow']), 3),
        'bleedthrough_score': round(_clamp(base['bleed'] + mod['bleed']), 3),
        'text_scale_score': round(_clamp(text_scale_score), 3),
    }


def _zone_recommendations(zone: str, quality: dict[str, float], minimal_processing: bool) -> tuple[list[str], list[str], str, str]:
    recommended: list[str] = []
    blocked: list[str] = []
    reasons: list[str] = []

    if minimal_processing:
        blocked.extend(['heavy_thresholding', 'aggressive_sharpen', 'zone_dewarp'])
        return [], blocked, 'low', 'stable_receipt_minimal_processing_prevents_regression'

    if quality['contrast_score'] < 0.42:
        recommended.append('local_contrast_enhancement')
        reasons.append('low_local_contrast')
    else:
        blocked.append('heavy_contrast_boost')

    if quality['sharpness_score'] < 0.34:
        recommended.append('local_sharpen')
        reasons.append('low_local_sharpness')
    else:
        blocked.append('aggressive_sharpen')

    if quality['shadow_score'] >= 0.48:
        recommended.append('local_shadow_suppression')
        reasons.append('local_shadow_risk')

    if quality['bleedthrough_score'] >= 0.48:
        recommended.append('local_bleedthrough_suppression')
        reasons.append('local_bleedthrough_risk')
    else:
        blocked.append('bleedthrough_suppression')

    if quality['text_scale_score'] < 0.70:
        if zone == 'article_amount_zone':
            recommended.append('scale_up_amount_column')
        elif zone == 'article_product_zone':
            recommended.append('scale_up_product_zone')
        else:
            recommended.append('local_scale_up')
        reasons.append('local_text_scale_too_small')
    else:
        blocked.append('unnecessary_scale_up')

    if zone in {'payment_zone', 'footer_noise_zone'}:
        if recommended:
            # Suppression rather than enhancement for noise-heavy non-article zones.
            recommended = [item for item in recommended if 'suppression' in item]
            blocked.extend(['product_text_enhancement', 'amount_column_enhancement'])
            reasons.append('non_article_zone_prefer_suppression')

    if not recommended:
        recommended.append('no_local_correction')
        reasons.append('zone_quality_sufficient_or_regression_risk_higher_than_gain')

    risk_score = 0.0
    if 'heavy_thresholding' not in blocked and quality['shadow_score'] > 0.55:
        risk_score += 0.25
    if quality['bleedthrough_score'] > 0.55:
        risk_score += 0.25
    if len(recommended) >= 3:
        risk_score += 0.25
    if zone in {'payment_zone', 'footer_noise_zone'}:
        risk_score += 0.15
    risk = 'high' if risk_score >= 0.55 else ('medium' if risk_score >= 0.25 else 'low')
    return recommended, sorted(set(blocked)), risk, '_and_'.join(reasons[:4])


def _overall_strategy(zones: list[dict[str, Any]], minimal_processing: bool) -> dict[str, Any]:
    if minimal_processing:
        return {
            'strategy': 'minimal_processing',
            'reason': 'stable_receipt_detected_local_heavy_preprocessing_blocked',
        }
    article_needs = [z for z in zones if z['zone'] in {'article_product_zone', 'article_amount_zone'} and z['recommended_local_correction'] != ['no_local_correction']]
    suppressed = [z for z in zones if z['zone'] in {'payment_zone', 'footer_noise_zone'} and any('suppression' in c for c in z['recommended_local_correction'])]
    if article_needs and suppressed:
        return {
            'strategy': 'selective_zone_enhancement_and_noise_suppression',
            'reason': 'article_zones_need_enhancement_while_payment_footer_zones_should_be_suppressed',
        }
    if article_needs:
        return {
            'strategy': 'selective_zone_enhancement',
            'reason': 'article_zones_need_local_enhancement',
        }
    return {
        'strategy': 'no_zone_preprocessing_integration_recommended',
        'reason': 'zone_level_gain_not_clear_enough_or_regression_risk_dominates',
    }


def build_zone_aware_preprocessing_diagnostics(receipt_json: dict[str, Any]) -> dict[str, Any]:
    governance = receipt_json.get('metadata', {}).get('pre_ocr_image_correction_governance', {})
    minimal = bool((governance.get('image_quality_findings') or {}).get('minimal_processing_recommended'))
    base = _base_quality(receipt_json)
    zones = []
    for zone in ZONES:
        quality = _zone_quality(base, zone)
        recommended, blocked, risk, reason = _zone_recommendations(zone, quality, minimal)
        zones.append({
            'zone': zone,
            'local_quality': quality,
            'recommended_local_correction': recommended,
            'blocked_local_corrections': blocked,
            'zone_regression_risk': risk,
            'reason': reason,
            'diagnostic_only': True,
            'parser_output_changed': False,
            'csv_output_changed': False,
        })
    return {
        'diagnostic_scope': 'zone_aware_adaptive_preprocessing_diagnostics',
        'diagnostic_only': True,
        'parser_output_changed': False,
        'csv_output_changed': False,
        'zones': zones,
        'overall_zone_strategy': _overall_strategy(zones, minimal),
        'rules': {
            'generic_geometric_zones_only': True,
            'store_specific_zones_used': False,
            'zone_corrections_applied_to_parser_input': False,
            'debug_images_pushed': False,
        },
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')
    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('zone_aware_preprocessing_diagnostics', {})
    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            if not json_path.exists():
                skipped += 1
                continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_zone_aware_preprocessing_diagnostics(payload)
        payload.setdefault('metadata', {})['zone_aware_preprocessing_diagnostics'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['zone_aware_preprocessing_diagnostics'][payload.get('metadata', {}).get('source_file', f'{target}.json')] = diagnostics
        processed += 1
    summary['schema_version'] = 'receipt-ocr-benchmark-v39-zone-aware-preprocessing-diagnostics'
    summary['zone_aware_preprocessing_diagnostics_processed_receipts'] = processed
    summary['zone_aware_preprocessing_diagnostics_skipped_receipts'] = skipped
    summary['zone_aware_preprocessing_diagnostics_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Zone-aware preprocessing diagnostics added for {processed} receipts; skipped={skipped}')


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
