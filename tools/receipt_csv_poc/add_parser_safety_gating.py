from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
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
MIN_ACCEPT_SCORE = Decimal('0.86')
MIN_ACCEPT_ROUTE_SUPPORT = 2
MIN_ACCEPT_CONSENSUS_CONFIDENCE = Decimal('0.72')
MAX_TOTAL_DELTA_FOR_LOW_SEVERITY = Decimal('25.00')


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


def _dec(value: Any, default: Decimal = Decimal('0')) -> Decimal:
    try:
        if value is None or value == '':
            return default
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return default


def _score(value: Any) -> Decimal:
    try:
        if value is None or value == '':
            return Decimal('0')
        return Decimal(str(value)).quantize(Decimal('0.001'))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _float(value: Decimal) -> float:
    return float(value)


def _conflict_severity(integration: dict[str, Any], candidate: dict[str, Any] | None = None) -> str:
    conflict_count = int(integration.get('integration_diff', {}).get('conflict_count') or 0)
    duplicate_count = int(integration.get('integration_diff', {}).get('duplicate_candidate_count') or 0)
    total_delta = abs(_dec(integration.get('integration_diff', {}).get('simulated_total_delta')))
    candidate_amount = abs(_dec((candidate or {}).get('amount')))
    if conflict_count > 0:
        return 'high'
    if duplicate_count > 0:
        return 'medium'
    if total_delta > MAX_TOTAL_DELTA_FOR_LOW_SEVERITY:
        return 'medium'
    if candidate_amount > Decimal('20.00'):
        return 'medium'
    return 'low'


def _candidate_safety_score(candidate: dict[str, Any], integration: dict[str, Any]) -> Decimal:
    weighted = _score(candidate.get('consensus_weighted_score'))
    consensus = _score(candidate.get('consensus_confidence'))
    route_support = Decimal(min(4, int(candidate.get('route_support_count') or 0))) / Decimal('4')
    conflict_penalty = Decimal('0')
    severity = _conflict_severity(integration, candidate)
    if severity == 'medium':
        conflict_penalty = Decimal('0.10')
    elif severity == 'high':
        conflict_penalty = Decimal('0.28')
    score = weighted * Decimal('0.55') + consensus * Decimal('0.25') + route_support * Decimal('0.20') - conflict_penalty
    if score < 0:
        score = Decimal('0')
    if score > 1:
        score = Decimal('1')
    return score.quantize(Decimal('0.001'))


def _decision(candidate: dict[str, Any], integration: dict[str, Any]) -> tuple[str, str, Decimal, str]:
    risk = str(candidate.get('risk_level') or '').lower()
    weighted = _score(candidate.get('consensus_weighted_score'))
    consensus = _score(candidate.get('consensus_confidence'))
    route_support = int(candidate.get('route_support_count') or 0)
    severity = _conflict_severity(integration, candidate)
    safety_score = _candidate_safety_score(candidate, integration)

    if severity == 'high':
        return 'blocked', 'high_parser_conflict_severity', safety_score, severity
    if risk != 'low':
        return 'blocked', 'risk_level_not_low', safety_score, severity
    if weighted < MIN_ACCEPT_SCORE:
        return 'blocked', 'consensus_weighted_score_below_accept_threshold', safety_score, severity
    if route_support < MIN_ACCEPT_ROUTE_SUPPORT:
        return 'blocked', 'insufficient_route_support', safety_score, severity
    if consensus < MIN_ACCEPT_CONSENSUS_CONFIDENCE:
        return 'blocked', 'consensus_confidence_below_accept_threshold', safety_score, severity
    if safety_score < MIN_ACCEPT_SCORE:
        return 'blocked', 'safety_score_below_accept_threshold', safety_score, severity
    return 'accept_for_future_integration', 'low_risk_high_consensus_no_conflict', safety_score, severity


def _duplicate_blocks(integration: dict[str, Any]) -> list[dict[str, Any]]:
    blocked = []
    for row in integration.get('duplicate_candidates', []) or []:
        blocked.append({
            'product_name': row.get('product_name'),
            'amount': row.get('amount'),
            'decision': 'blocked',
            'reject_reason': 'duplicate_candidate_never_accepted',
            'parser_conflict_severity': 'medium',
            'diagnostic_only': True,
            'parser_output_changed': False,
            'csv_output_changed': False,
        })
    return blocked


def _conflict_blocks(integration: dict[str, Any]) -> list[dict[str, Any]]:
    blocked = []
    for row in integration.get('conflicting_rows', []) or []:
        blocked.append({
            'product_name': row.get('product_name'),
            'amount': row.get('amount'),
            'decision': 'blocked',
            'reject_reason': row.get('conflict_reason') or 'parser_conflict',
            'parser_conflict_severity': 'high',
            'diagnostic_only': True,
            'parser_output_changed': False,
            'csv_output_changed': False,
        })
    return blocked


def _readiness(candidate_decisions: list[dict[str, Any]], blocked: list[dict[str, Any]], integration: dict[str, Any]) -> dict[str, Any]:
    accepted = [row for row in candidate_decisions if row.get('decision') == 'accept_for_future_integration']
    high_blocks = [row for row in blocked if row.get('parser_conflict_severity') == 'high']
    total_candidates = max(1, len(candidate_decisions) + len(blocked))
    accept_ratio = Decimal(len(accepted)) / Decimal(total_candidates)
    high_penalty = Decimal(len(high_blocks)) / Decimal(total_candidates)
    coverage_signal = Decimal(min(1.0, float(len(accepted)) / 3.0))
    score = accept_ratio * Decimal('0.45') + coverage_signal * Decimal('0.35') + (Decimal('1') - high_penalty) * Decimal('0.20')
    if score < 0:
        score = Decimal('0')
    if score > 1:
        score = Decimal('1')
    score = score.quantize(Decimal('0.001'))
    ready = bool(score >= Decimal('0.85') and len(high_blocks) == 0 and len(accepted) >= 3)
    if ready:
        reason = 'sufficient_low_risk_candidates_without_high_conflicts'
    elif high_blocks:
        reason = 'high_conflict_candidates_block_controlled_integration'
    elif len(accepted) == 0:
        reason = 'no_candidates_safe_enough_for_integration'
    else:
        reason = 'requires_more_receipt_coverage_before_parser_change'
    return {
        'parser_integration_readiness_score': _float(score),
        'ready_for_controlled_integration': ready,
        'readiness_reason': reason,
        'accepted_candidate_count': len(accepted),
        'blocked_candidate_count': len(blocked),
        'high_conflict_block_count': len(high_blocks),
        'integration_allowed': False,
    }


def build_parser_safety_gating(receipt_json: dict[str, Any]) -> dict[str, Any]:
    integration = receipt_json.get('metadata', {}).get('simulated_parser_integration', {})
    source_rows = integration.get('simulated_added_rows', []) or []
    decisions = []
    blocked = []

    for row in source_rows:
        decision, reason, safety_score, severity = _decision(row, integration)
        output = {
            'product_name': row.get('product_name'),
            'amount': row.get('amount'),
            'decision': decision,
            'safety_score': _float(safety_score),
            'decision_reason': reason if decision != 'blocked' else None,
            'reject_reason': reason if decision == 'blocked' else None,
            'risk_level': row.get('risk_level'),
            'consensus_weighted_score': row.get('consensus_weighted_score'),
            'route_support_count': row.get('route_support_count'),
            'consensus_confidence': row.get('consensus_confidence'),
            'parser_conflict_severity': severity,
            'diagnostic_only': True,
            'parser_output_changed': False,
            'csv_output_changed': False,
        }
        if decision == 'accept_for_future_integration':
            decisions.append(output)
        else:
            blocked.append(output)

    blocked.extend(_duplicate_blocks(integration))
    blocked.extend(_conflict_blocks(integration))
    readiness = _readiness(decisions, blocked, integration)

    return {
        'diagnostic_scope': 'parser_safety_gating_for_simulated_additions',
        'diagnostic_only': True,
        'parser_output_changed': False,
        'csv_output_changed': False,
        'integration_allowed': False,
        'candidate_decisions': decisions,
        'blocked_candidates': blocked,
        'readiness': readiness,
        'rules': {
            'only_simulated_added_rows_evaluated_for_acceptance': True,
            'duplicates_never_accepted': True,
            'min_accept_score': _float(MIN_ACCEPT_SCORE),
            'min_accept_route_support': MIN_ACCEPT_ROUTE_SUPPORT,
            'min_accept_consensus_confidence': _float(MIN_ACCEPT_CONSENSUS_CONFIDENCE),
            'parser_input_changed': False,
            'csv_output_changed': False,
        },
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')
    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('parser_safety_gating', {})
    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_parser_safety_gating(payload)
        payload.setdefault('metadata', {})['parser_safety_gating'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['parser_safety_gating'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1
    summary['schema_version'] = 'receipt-ocr-benchmark-v36-parser-safety-gating'
    summary['parser_safety_gating_processed_receipts'] = processed
    summary['parser_safety_gating_skipped_receipts'] = skipped
    summary['parser_safety_gating_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Parser safety gating diagnostics added for {processed} receipts; skipped={skipped}')


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
