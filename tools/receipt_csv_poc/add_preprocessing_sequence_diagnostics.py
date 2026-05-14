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
GEOMETRY_STEPS = {'document_isolation_crop', 'deskew', 'perspective_correction'}
LOCAL_ENHANCEMENT_STEPS = {
    'local_contrast_enhancement',
    'local_sharpen',
    'scale_up_amount_column',
    'scale_up_product_zone',
    'local_scale_up',
}
NOISE_STEPS = {'local_shadow_suppression', 'local_bleedthrough_suppression'}
DANGEROUS_STEPS = {'aggressive_sharpen', 'heavy_thresholding', 'heavy_contrast_boost'}


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


def _recommendation(risk: str, benefit: float) -> str:
    if risk == 'high':
        return 'block_for_now'
    if benefit >= 0.55 and risk == 'low':
        return 'allow_diagnostic_only'
    if benefit >= 0.65 and risk == 'medium':
        return 'allow_diagnostic_only'
    return 'needs_more_evidence'


def _governance_steps(receipt_json: dict[str, Any]) -> list[str]:
    governance = receipt_json.get('metadata', {}).get('pre_ocr_image_correction_governance', {})
    safe_route = governance.get('safe_route', {}) or {}
    route_name = str(safe_route.get('route_name') or '')
    if route_name == 'minimal_processing':
        return ['minimal_processing']
    steps = []
    for item in governance.get('recommended_corrections', []) or []:
        correction = item.get('correction')
        if correction and correction != 'minimal_processing':
            steps.append(str(correction))
    for part in route_name.split('_'):
        # Preserve known combined names via later zone additions; single fragments are ignored.
        pass
    return _dedupe(steps)


def _zone_steps(receipt_json: dict[str, Any]) -> list[str]:
    zone_diag = receipt_json.get('metadata', {}).get('zone_aware_preprocessing_diagnostics', {})
    steps = []
    for zone in zone_diag.get('zones', []) or []:
        for correction in zone.get('recommended_local_correction', []) or []:
            if correction not in {'no_local_correction', 'minimal_processing'}:
                steps.append(str(correction))
    return _dedupe(steps)


def _blocked_steps(receipt_json: dict[str, Any]) -> list[str]:
    out = []
    governance = receipt_json.get('metadata', {}).get('pre_ocr_image_correction_governance', {})
    for item in governance.get('blocked_corrections', []) or []:
        if item.get('correction'):
            out.append(str(item.get('correction')))
    zone_diag = receipt_json.get('metadata', {}).get('zone_aware_preprocessing_diagnostics', {})
    for zone in zone_diag.get('zones', []) or []:
        out.extend(str(item) for item in zone.get('blocked_local_corrections', []) or [])
    interference = receipt_json.get('metadata', {}).get('cross_zone_interference_diagnostics', {})
    for item in interference.get('blocked_zone_corrections', []) or []:
        if item.get('correction'):
            out.append(str(item.get('correction')))
    return _dedupe(out)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _ordered_sequence(steps: list[str]) -> list[str]:
    order = []
    for group in (GEOMETRY_STEPS, NOISE_STEPS, LOCAL_ENHANCEMENT_STEPS):
        order.extend([step for step in steps if step in group])
    order.extend([step for step in steps if step not in order])
    return _dedupe(order)


def _benefit_signal(receipt_json: dict[str, Any], steps: list[str]) -> float:
    simulation = receipt_json.get('metadata', {}).get('adaptive_preprocessing_simulation', {})
    delta = simulation.get('delta', {}) or {}
    structural = max(0, _as_float(delta.get('normalized_group_delta'))) / 6.0
    consensus = max(0, _as_float(delta.get('consensus_group_delta'))) / 4.0
    readiness = max(0, _as_float(delta.get('parser_readiness_delta'))) / 0.35
    step_bonus = min(0.25, len([step for step in steps if step != 'minimal_processing']) * 0.04)
    return round(min(1.0, structural * 0.30 + consensus * 0.25 + readiness * 0.30 + step_bonus), 3)


def _interference_risk(receipt_json: dict[str, Any], steps: list[str]) -> tuple[float, list[str]]:
    interference = receipt_json.get('metadata', {}).get('cross_zone_interference_diagnostics', {})
    pairs = interference.get('interference_pairs', []) or []
    relevant = [pair for pair in pairs if pair.get('correction') in steps]
    if not relevant:
        return 0.12 if steps != ['minimal_processing'] else 0.02, []
    max_risk = max(_as_float(pair.get('interference_risk_score')) for pair in relevant)
    high_count = sum(1 for pair in relevant if pair.get('cross_zone_regression_risk') == 'high')
    affected = sorted({signal for pair in relevant for signal in pair.get('affected_signals', [])})
    risk = min(1.0, max_risk + high_count * 0.08)
    return round(risk, 3), affected[:12]


def _candidate_sequence(receipt_json: dict[str, Any], sequence_id: str, steps: list[str], reason: str) -> dict[str, Any]:
    steps = _ordered_sequence(_dedupe(steps))
    benefit = _benefit_signal(receipt_json, steps)
    risk_score, affected = _interference_risk(receipt_json, steps)
    risk = _risk(risk_score)
    return {
        'sequence_id': sequence_id,
        'steps': steps,
        'required_preconditions': _required_preconditions(steps),
        'sequence_benefit_score': benefit,
        'sequence_interference_risk_score': risk_score,
        'sequence_regression_risk': risk,
        'sequence_recommendation': _recommendation(risk, benefit),
        'sequencing_reason': reason,
        'affected_signals': affected,
        'diagnostic_only': True,
        'parser_output_changed': False,
        'csv_output_changed': False,
    }


def _required_preconditions(steps: list[str]) -> list[str]:
    preconditions = []
    if any(step in LOCAL_ENHANCEMENT_STEPS for step in steps):
        preconditions.append('geometry_steps_completed_before_local_enhancement')
    if any('threshold' in step for step in steps):
        preconditions.append('noise_amplification_steps_not_run_before_thresholding')
    if any('bleedthrough' in step for step in steps):
        preconditions.append('thin_text_loss_risk_checked')
    if 'minimal_processing' in steps:
        preconditions.append('stable_receipt_detected')
    return preconditions


def _forbidden_sequences(blocked_steps: list[str]) -> list[dict[str, Any]]:
    forbidden = [
        {
            'steps': ['aggressive_sharpen', 'heavy_thresholding'],
            'block_reason': 'noise_amplification_before_thresholding',
        },
        {
            'steps': ['heavy_thresholding', 'scale_up_amount_column'],
            'block_reason': 'threshold_noise_then_scale_up_creates_pseudo_amounts',
        },
        {
            'steps': ['local_bleedthrough_suppression', 'aggressive_sharpen'],
            'block_reason': 'thin_thermal_text_loss_followed_by_noise_amplification',
        },
    ]
    for step in blocked_steps:
        if step in DANGEROUS_STEPS or 'heavy' in step or 'aggressive' in step:
            forbidden.append({
                'steps': [step],
                'block_reason': 'blocked_by_q10_q12_q13_regression_governance',
            })
    out = []
    seen = set()
    for item in forbidden:
        key = tuple(item['steps'])
        if key not in seen:
            seen.add(key)
            out.append({**item, 'diagnostic_only': True, 'parser_output_changed': False, 'csv_output_changed': False})
    return out


def build_preprocessing_sequence_diagnostics(receipt_json: dict[str, Any]) -> dict[str, Any]:
    governance = receipt_json.get('metadata', {}).get('pre_ocr_image_correction_governance', {})
    minimal = bool((governance.get('image_quality_findings') or {}).get('minimal_processing_recommended'))
    gov_steps = _governance_steps(receipt_json)
    zone_steps = _zone_steps(receipt_json)
    blocked = _blocked_steps(receipt_json)

    candidate_sequences = []
    if minimal or gov_steps == ['minimal_processing']:
        candidate_sequences.append(_candidate_sequence(receipt_json, 'seq_001', ['minimal_processing'], 'stable_receipt_minimal_processing_prevents_regression'))
    else:
        combined = _dedupe(gov_steps + zone_steps)
        geometry_first = _ordered_sequence(combined)
        if geometry_first:
            candidate_sequences.append(_candidate_sequence(receipt_json, 'seq_001', geometry_first, 'geometry_before_local_enhancement_limits_spillover'))
        conservative = [step for step in geometry_first if step in GEOMETRY_STEPS or step in {'local_contrast_enhancement', 'scale_up_amount_column', 'scale_up_product_zone'}]
        if conservative and conservative != geometry_first:
            candidate_sequences.append(_candidate_sequence(receipt_json, 'seq_002', conservative, 'conservative_sequence_excludes_noise_amplifying_steps'))
        local_only = [step for step in geometry_first if step in LOCAL_ENHANCEMENT_STEPS]
        if local_only:
            candidate_sequences.append(_candidate_sequence(receipt_json, 'seq_003', local_only, 'local_only_sequence_requires_more_evidence_due_to_missing_geometry_preconditions'))

    forbidden = _forbidden_sequences(blocked)
    allowed = [seq for seq in candidate_sequences if seq.get('sequence_recommendation') == 'allow_diagnostic_only']
    blocked_seq = [seq for seq in candidate_sequences if seq.get('sequence_recommendation') == 'block_for_now']
    needs = [seq for seq in candidate_sequences if seq.get('sequence_recommendation') == 'needs_more_evidence']
    return {
        'diagnostic_scope': 'preprocessing_sequence_diagnostics',
        'diagnostic_only': True,
        'parser_output_changed': False,
        'csv_output_changed': False,
        'candidate_sequences': candidate_sequences,
        'forbidden_sequences': forbidden,
        'sequence_summary': {
            'allow_diagnostic_only_count': len(allowed),
            'needs_more_evidence_count': len(needs),
            'block_for_now_count': len(blocked_seq),
            'forbidden_sequence_count': len(forbidden),
            'recommended_sequence_id': allowed[0]['sequence_id'] if allowed else '',
            'overall_recommendation': 'allow_diagnostic_only' if allowed else ('needs_more_evidence' if needs else 'block_for_now'),
        },
        'rules': {
            'sequencing_only': True,
            'real_preprocessing_executed': False,
            'parser_input_changed': False,
            'csv_output_changed': False,
            'geometry_before_local_enhancement': True,
            'noise_amplifying_steps_before_thresholding_blocked': True,
        },
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')
    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('preprocessing_sequence_diagnostics', {})
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
        diagnostics = build_preprocessing_sequence_diagnostics(payload)
        payload.setdefault('metadata', {})['preprocessing_sequence_diagnostics'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['preprocessing_sequence_diagnostics'][payload.get('metadata', {}).get('source_file', f'{target}.json')] = diagnostics
        processed += 1
    summary['schema_version'] = 'receipt-ocr-benchmark-v41-preprocessing-sequence-diagnostics'
    summary['preprocessing_sequence_diagnostics_processed_receipts'] = processed
    summary['preprocessing_sequence_diagnostics_skipped_receipts'] = skipped
    summary['preprocessing_sequence_diagnostics_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Preprocessing sequence diagnostics added for {processed} receipts; skipped={skipped}')


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
