from __future__ import annotations

import argparse
import json
import re
from difflib import SequenceMatcher
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
MIN_TEXT_SIMILARITY = 0.58
MIN_ROUTE_SUPPORT_FOR_CONSENSUS = 2


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


def _norm(text: Any) -> str:
    text = str(text or '').lower()
    text = re.sub(r'[^a-z0-9à-ÿ]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _amount_key(amounts: list[Any], amount_text: Any = '') -> str:
    if amounts:
        return str(amounts[0]).replace(',', '.').strip()
    text = str(amount_text or '').replace(',', '.')
    match = re.search(r'-?\d+\.\d{2}', text)
    return match.group(0) if match else ''


def _text_similarity(a: str, b: str) -> float:
    a_norm = _norm(a)
    b_norm = _norm(b)
    if not a_norm or not b_norm:
        return 0.0
    seq = SequenceMatcher(None, a_norm, b_norm).ratio()
    a_tokens = set(a_norm.split())
    b_tokens = set(b_norm.split())
    token_overlap = len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))
    return round((seq * 0.65) + (token_overlap * 0.35), 3)


def _route_label(route: str, ocr_config: str = '') -> str:
    return f'{route} + {ocr_config or "unknown_ocr_config"}'


def _signals_from_route_candidates(receipt_json: dict[str, Any]) -> list[dict[str, Any]]:
    orchestration = receipt_json.get('metadata', {}).get('adaptive_ocr_orchestration', {})
    structural = receipt_json.get('metadata', {}).get('ocr_structural_normalization', {})
    signals: list[dict[str, Any]] = []

    # Q5 route candidates do not store full text groups per variant yet. Use route-level counts plus
    # Q3 normalized groups as text/amount anchors, and annotate them with each route that produced signals.
    base_groups = structural.get('normalized_line_groups', []) or []
    for route in orchestration.get('route_candidates', []) or []:
        route_name = str(route.get('preprocessing_variant') or '')
        ocr_config = str(route.get('ocr_config') or '')
        route_score = float(route.get('route_score') or 0)
        if int(route.get('normalized_group_count') or 0) <= 0 and int(route.get('article_zone_amount_count') or 0) <= 0:
            continue
        for group in base_groups:
            text = str(group.get('normalized_text') or '')
            amount_key = _amount_key(group.get('linked_amounts') or [], group.get('linked_amount_text'))
            if not text and not amount_key:
                continue
            signals.append({
                'route': _route_label(route_name, ocr_config),
                'preprocessing_variant': route_name,
                'ocr_config': ocr_config,
                'route_score': route_score,
                'product_text': text,
                'amount_key': amount_key,
                'amount_text': group.get('linked_amount_text') or amount_key,
                'box': group.get('cluster_box') or group.get('linked_amount_box'),
                'group_id': group.get('group_id'),
                'source': 'adaptive_route_plus_structural_group',
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })
    return signals


def _signals_from_shadow(receipt_json: dict[str, Any]) -> list[dict[str, Any]]:
    shadow = receipt_json.get('metadata', {}).get('shadow_reconstruction_output', {})
    signals = []
    for row in shadow.get('generated_rows', []) or []:
        signals.append({
            'route': _route_label(str(row.get('variant') or 'shadow_low_risk'), 'scored_candidate'),
            'preprocessing_variant': row.get('variant') or 'shadow_low_risk',
            'ocr_config': 'scored_candidate',
            'route_score': float(row.get('reliability_score') or 0.0),
            'product_text': row.get('product_name') or '',
            'amount_key': _amount_key(row.get('amounts') or [], row.get('amount_text') or row.get('amount')),
            'amount_text': row.get('amount_text') or row.get('amount'),
            'box': None,
            'group_id': row.get('cluster_id'),
            'source': 'shadow_reconstruction_low_risk',
            'diagnostic_only': True,
            'reconstruction_applied': False,
        })
    return signals


def _same_consensus_bucket(a: dict[str, Any], b: dict[str, Any]) -> bool:
    amount_a = a.get('amount_key') or ''
    amount_b = b.get('amount_key') or ''
    amount_match = bool(amount_a and amount_b and amount_a == amount_b)
    text_sim = _text_similarity(str(a.get('product_text') or ''), str(b.get('product_text') or ''))
    if amount_match and text_sim >= 0.35:
        return True
    if text_sim >= MIN_TEXT_SIMILARITY and (amount_match or not amount_a or not amount_b):
        return True
    return False


def _cluster_signals(signals: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for signal in signals:
        placed = False
        for cluster in clusters:
            if any(_same_consensus_bucket(signal, existing) for existing in cluster):
                cluster.append(signal)
                placed = True
                break
        if not placed:
            clusters.append([signal])
    return clusters


def _consensus_confidence(cluster: list[dict[str, Any]]) -> float:
    routes = {signal.get('route') for signal in cluster}
    support_score = min(1.0, len(routes) / 4.0)
    avg_route_score = sum(float(signal.get('route_score') or 0) for signal in cluster) / max(1, len(cluster))
    amount_support = 1.0 if len({signal.get('amount_key') for signal in cluster if signal.get('amount_key')}) == 1 and any(signal.get('amount_key') for signal in cluster) else 0.45
    return round(max(0.0, min(1.0, support_score * 0.45 + avg_route_score * 0.35 + amount_support * 0.20)), 3)


def build_cross_route_ocr_consensus(receipt_json: dict[str, Any]) -> dict[str, Any]:
    signals = _signals_from_route_candidates(receipt_json) + _signals_from_shadow(receipt_json)
    clusters = _cluster_signals(signals)
    consensus_groups = []
    route_disagreements = []

    for index, cluster in enumerate(clusters, start=1):
        routes = sorted({str(signal.get('route')) for signal in cluster if signal.get('route')})
        product_texts = []
        for signal in cluster:
            text = str(signal.get('product_text') or '').strip()
            if text and text not in product_texts:
                product_texts.append(text)
        amount_candidates = sorted({str(signal.get('amount_key')) for signal in cluster if signal.get('amount_key')})
        support_count = len(routes)
        confidence = _consensus_confidence(cluster)
        if support_count >= MIN_ROUTE_SUPPORT_FOR_CONSENSUS:
            consensus_groups.append({
                'consensus_id': f'consensus_{len(consensus_groups) + 1:03d}',
                'product_text_candidates': product_texts,
                'amount_candidates': amount_candidates,
                'supporting_routes': routes,
                'route_support_count': support_count,
                'consensus_confidence': confidence,
                'consensus_reason': 'multi_route_product_amount_overlap' if amount_candidates else 'multi_route_product_text_overlap',
                'source_group_ids': [signal.get('group_id') for signal in cluster if signal.get('group_id')],
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })
        else:
            route_disagreements.append({
                'route': routes[0] if routes else 'unknown_route',
                'product_text_candidates': product_texts,
                'amount_candidates': amount_candidates,
                'disagreement_reason': 'single_route_signal_without_cross_route_support',
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })

    # Explicitly flag amount-only style disagreements.
    for signal in signals:
        if signal.get('amount_key') and not _norm(signal.get('product_text')):
            route_disagreements.append({
                'route': signal.get('route'),
                'amount_candidates': [signal.get('amount_key')],
                'disagreement_reason': 'amount_without_matching_product_consensus',
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })

    return {
        'diagnostic_scope': 'cross_route_ocr_product_amount_consensus',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'signal_count': len(signals),
        'consensus_group_count': len(consensus_groups),
        'route_disagreement_count': len(route_disagreements),
        'rules': {
            'min_text_similarity': MIN_TEXT_SIMILARITY,
            'min_route_support_for_consensus': MIN_ROUTE_SUPPORT_FOR_CONSENSUS,
            'parser_input_changed': False,
            'csv_output_changed': False,
        },
        'consensus_groups': consensus_groups,
        'route_disagreements': route_disagreements,
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')
    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('cross_route_ocr_consensus', {})
    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_cross_route_ocr_consensus(payload)
        payload.setdefault('metadata', {})['cross_route_ocr_consensus'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['cross_route_ocr_consensus'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1
    summary['schema_version'] = 'receipt-ocr-benchmark-v33-cross-route-ocr-consensus'
    summary['cross_route_ocr_consensus_processed_receipts'] = processed
    summary['cross_route_ocr_consensus_skipped_receipts'] = skipped
    summary['cross_route_ocr_consensus_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Cross-route OCR consensus diagnostics added for {processed} receipts; skipped={skipped}')


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
