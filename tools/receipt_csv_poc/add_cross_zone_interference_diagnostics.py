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
ZONE_ORDER = [
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


def _risk(score: float) -> str:
    if score >= 0.66:
        return 'high'
    if score >= 0.33:
        return 'medium'
    return 'low'


def _recommendation(risk_score: float, benefit_score: float) -> str:
    if risk_score >= 0.66:
        return 'block_for_now'
    if benefit_score >= 0.55 and risk_score <= 0.45:
        return 'allow_diagnostic_only'
    return 'needs_more_evidence'


def _zone_index(zone: str) -> int:
    try:
        return ZONE_ORDER.index(zone)
    except ValueError:
        return len(ZONE_ORDER)


def _adjacency_factor(source_zone: str, target_zone: str) -> float:
    distance = abs(_zone_index(source_zone) - _zone_index(target_zone))
    if distance == 0:
        return 1.0
    if distance == 1:
        return 0.72
    if distance == 2:
        return 0.42
    return 0.20


def _benefit_score(zone: dict[str, Any], correction: str) -> float:
    quality = zone.get('local_quality', {}) or {}
    contrast_need = 1.0 - _as_float(quality.get('contrast_score'), 0.5)
    sharp_need = 1.0 - _as_float(quality.get('sharpness_score'), 0.5)
    shadow = _as_float(quality.get('shadow_score'), 0.0)
    bleed = _as_float(quality.get('bleedthrough_score'), 0.0)
    scale_need = 1.0 - _as_float(quality.get('text_scale_score'), 0.5)
    if 'contrast' in correction:
        return round(min(1.0, contrast_need), 3)
    if 'sharpen' in correction:
        return round(min(1.0, sharp_need), 3)
    if 'shadow' in correction:
        return round(min(1.0, shadow), 3)
    if 'bleedthrough' in correction:
        return round(min(1.0, bleed), 3)
    if 'scale' in correction:
        return round(min(1.0, scale_need), 3)
    if 'suppression' in correction:
        return round(min(1.0, max(shadow, bleed)), 3)
    return 0.35


def _risk_score(source_zone: dict[str, Any], target_zone: dict[str, Any], correction: str) -> tuple[float, list[str]]:
    source = source_zone.get('zone', '')
    target = target_zone.get('zone', '')
    target_quality = target_zone.get('local_quality', {}) or {}
    source_quality = source_zone.get('local_quality', {}) or {}
    adjacency = _adjacency_factor(source, target)
    target_noise = max(_as_float(target_quality.get('shadow_score')), _as_float(target_quality.get('bleedthrough_score')))
    source_noise = max(_as_float(source_quality.get('shadow_score')), _as_float(source_quality.get('bleedthrough_score')))
    signals: list[str] = []
    base = 0.08 * adjacency

    if 'threshold' in correction:
        base += 0.34 * adjacency + 0.20 * target_noise
        signals.extend(['pseudo_amount_noise', 'threshold_spillover'])
    if 'sharpen' in correction:
        base += 0.28 * adjacency + 0.22 * max(source_noise, target_noise)
        signals.extend(['noise_amplification', 'thermoprint_fragment_amplification'])
    if 'scale' in correction:
        base += 0.18 * adjacency
        if target in {'payment_zone', 'footer_noise_zone'}:
            base += 0.18
            signals.append('footer_payment_text_bleed')
        signals.append('pseudo_amount_noise')
    if 'shadow' in correction or 'suppression' in correction:
        base += 0.16 * adjacency
        if target in {'article_product_zone', 'article_amount_zone'}:
            base += 0.16
            signals.append('thin_text_suppression_risk')
        signals.append('local_text_loss')
    if 'bleedthrough' in correction:
        base += 0.16 * adjacency
        if target in {'article_product_zone', 'article_amount_zone'}:
            base += 0.12
            signals.append('real_text_removed_as_bleedthrough')
        signals.append('backside_text_suppression')
    if 'contrast' in correction:
        base += 0.12 * adjacency + 0.08 * target_noise
        signals.append('contrast_noise_boost')
    if source in {'payment_zone', 'footer_noise_zone'} and target in {'article_product_zone', 'article_amount_zone'}:
        base += 0.16
        signals.append('non_article_zone_near_article_spillover')
    if source == target:
        base *= 0.72
        signals.append('same_zone_localized_effect')

    return round(min(1.0, base), 3), sorted(set(signals))


def _blocked_reason(zone: str, correction: str, reason: str = '') -> str:
    if 'sharpen' in correction:
        return 'high_noise_amplification_risk'
    if 'threshold' in correction:
        return 'threshold_spillover_or_pseudo_amount_risk'
    if 'scale' in correction:
        return 'scale_up_may_introduce_extra_ocr_noise'
    if 'bleedthrough' in correction:
        return 'bleedthrough_suppression_may_remove_real_thermal_text'
    return reason or 'zone_correction_blocked_by_q12_regression_risk'


def build_cross_zone_interference_diagnostics(receipt_json: dict[str, Any]) -> dict[str, Any]:
    zone_diag = receipt_json.get('metadata', {}).get('zone_aware_preprocessing_diagnostics', {})
    zones = zone_diag.get('zones', []) or []
    zone_by_name = {zone.get('zone'): zone for zone in zones}
    interference_pairs = []
    blocked_zone_corrections = []

    for source in zones:
        source_zone = source.get('zone')
        corrections = source.get('recommended_local_correction') or []
        for blocked in source.get('blocked_local_corrections') or []:
            if blocked == 'no_local_correction':
                continue
            blocked_zone_corrections.append({
                'source_zone': source_zone,
                'correction': blocked,
                'block_reason': _blocked_reason(str(source_zone), str(blocked)),
                'diagnostic_only': True,
                'parser_output_changed': False,
                'csv_output_changed': False,
            })
        for correction in corrections:
            if correction in {'no_local_correction', 'minimal_processing'}:
                continue
            benefit = _benefit_score(source, correction)
            for target in zones:
                target_zone = target.get('zone')
                if not target_zone:
                    continue
                risk_score, affected = _risk_score(source, target, correction)
                interference_pairs.append({
                    'source_zone': source_zone,
                    'target_zone': target_zone,
                    'correction': correction,
                    'expected_benefit_score': benefit,
                    'interference_risk_score': risk_score,
                    'cross_zone_regression_risk': _risk(risk_score),
                    'affected_signals': affected,
                    'recommendation': _recommendation(risk_score, benefit),
                    'diagnostic_only': True,
                    'parser_output_changed': False,
                    'csv_output_changed': False,
                })

    high_risk_pairs = [pair for pair in interference_pairs if pair.get('cross_zone_regression_risk') == 'high']
    allow_pairs = [pair for pair in interference_pairs if pair.get('recommendation') == 'allow_diagnostic_only']
    needs_more = [pair for pair in interference_pairs if pair.get('recommendation') == 'needs_more_evidence']
    return {
        'diagnostic_scope': 'cross_zone_preprocessing_interference_risk_analysis',
        'diagnostic_only': True,
        'parser_output_changed': False,
        'csv_output_changed': False,
        'interference_pair_count': len(interference_pairs),
        'high_risk_interference_pair_count': len(high_risk_pairs),
        'allowed_diagnostic_pair_count': len(allow_pairs),
        'needs_more_evidence_pair_count': len(needs_more),
        'interference_pairs': interference_pairs,
        'blocked_zone_corrections': blocked_zone_corrections,
        'overall_interference_assessment': {
            'recommendation': 'block_zone_preprocessing_integration' if high_risk_pairs else ('needs_more_evidence' if needs_more else 'allow_diagnostic_only'),
            'reason': 'high_risk_cross_zone_interference_detected' if high_risk_pairs else ('insufficient_evidence_for_safe_zone_integration' if needs_more else 'no_high_risk_interference_detected'),
        },
        'rules': {
            'source_diagnostics': 'zone_aware_preprocessing_diagnostics',
            'interference_only': True,
            'real_zone_preprocessing_executed': False,
            'parser_input_changed': False,
            'csv_output_changed': False,
            'recommendations': ['allow_diagnostic_only', 'block_for_now', 'needs_more_evidence'],
        },
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')
    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('cross_zone_interference_diagnostics', {})
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
        diagnostics = build_cross_zone_interference_diagnostics(payload)
        payload.setdefault('metadata', {})['cross_zone_interference_diagnostics'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['cross_zone_interference_diagnostics'][payload.get('metadata', {}).get('source_file', f'{target}.json')] = diagnostics
        processed += 1
    summary['schema_version'] = 'receipt-ocr-benchmark-v40-cross-zone-interference-diagnostics'
    summary['cross_zone_interference_diagnostics_processed_receipts'] = processed
    summary['cross_zone_interference_diagnostics_skipped_receipts'] = skipped
    summary['cross_zone_interference_diagnostics_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Cross-zone interference diagnostics added for {processed} receipts; skipped={skipped}')


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
