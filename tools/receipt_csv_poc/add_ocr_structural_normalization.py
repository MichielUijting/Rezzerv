from __future__ import annotations

import argparse
import json
import re
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
AMOUNT_PATTERN = re.compile(r'(?<!\d)(?:€|eur|euro)?\s*(-?\d+[\.,]\d{2})(?!\d)', re.IGNORECASE)
BLOCKED_ZONE_REASONS = (
    'payment', 'total', 'vat', 'btw', 'terminal', 'merchant', 'kaart', 'pin',
    'zegel', 'campagne', 'loyalty', 'wisselgeld', 'subtotaal'
)
MAX_CLUSTER_AMOUNT_BASELINE_DISTANCE = 72
MIN_GROUP_CONFIDENCE = 0.30


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


def _norm(text: Any) -> str:
    text = str(text or '').lower()
    text = re.sub(r'[^a-z0-9à-ÿ]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _amounts(text: str) -> list[str]:
    return [match.group(1).replace(',', '.') for match in AMOUNT_PATTERN.finditer(text or '')]


def _box_center_y(box: dict[str, Any] | None) -> int:
    if not box:
        return 0
    return int(box.get('center_y', int(box.get('top', 0)) + int(box.get('height', 0)) // 2))


def _box_left(box: dict[str, Any] | None) -> int:
    return int((box or {}).get('left', 0))


def _box_right(box: dict[str, Any] | None) -> int:
    box = box or {}
    return int(box.get('right', int(box.get('left', 0)) + int(box.get('width', 0))))


def _union_box(boxes: list[dict[str, Any]]) -> dict[str, int] | None:
    boxes = [box for box in boxes if box]
    if not boxes:
        return None
    left = min(int(box.get('left', 0)) for box in boxes)
    top = min(int(box.get('top', 0)) for box in boxes)
    right = max(int(box.get('right', int(box.get('left', 0)) + int(box.get('width', 0)))) for box in boxes)
    bottom = max(int(box.get('bottom', int(box.get('top', 0)) + int(box.get('height', 0)))) for box in boxes)
    return {
        'left': left,
        'top': top,
        'right': right,
        'bottom': bottom,
        'width': right - left,
        'height': bottom - top,
        'center_x': int((left + right) / 2),
        'center_y': int((top + bottom) / 2),
    }


def _is_noise_text(text: str) -> bool:
    normalized = _norm(text)
    if not normalized or len(normalized) < 3:
        return True
    if any(token in normalized for token in BLOCKED_ZONE_REASONS):
        return True
    alpha_count = len(re.findall(r'[a-zà-ÿ]', normalized))
    return alpha_count < 3


def _broken_word_join_hints(lines: list[str]) -> list[str]:
    tokens = []
    for line in lines:
        tokens.extend([token for token in _norm(line).split() if re.search(r'[a-zà-ÿ]', token)])
    hints = []
    for index in range(len(tokens) - 1):
        left, right = tokens[index], tokens[index + 1]
        if 1 <= len(left) <= 3 and len(right) >= 3:
            hints.append(f'{left} {right} -> {left}{right}')
        elif len(left) >= 3 and 1 <= len(right) <= 3:
            hints.append(f'{left} {right} -> {left}{right}')
    return hints[:8]


def _structural_confidence(cluster: dict[str, Any], amount: dict[str, Any] | None, stability_lookup: dict[str, dict[str, Any]]) -> float:
    cluster_id = str(cluster.get('cluster_id') or '')
    stability = stability_lookup.get(cluster_id, {})
    cluster_conf = float(cluster.get('cluster_confidence') or 50.0) / 100.0
    text_stability = float(stability.get('text_stability_score') or 0.50)
    linked_bonus = 0.18 if amount else 0.0
    noise_penalty = min(0.25, float(stability.get('pseudo_amount_noise_count') or 0) * 0.08)
    score = (cluster_conf * 0.35) + (text_stability * 0.35) + linked_bonus + 0.12 - noise_penalty
    return round(max(0.0, min(1.0, score)), 3)


def _stability_lookup(receipt_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    diag = receipt_json.get('metadata', {}).get('ocr_text_stability_diagnostics', {})
    return {str(cluster.get('cluster_id')): cluster for cluster in diag.get('clusters', [])}


def _article_amounts(receipt_json: dict[str, Any]) -> list[dict[str, Any]]:
    zone_diag = receipt_json.get('metadata', {}).get('amount_region_zone_diagnostics', {})
    out = []
    for variant in zone_diag.get('variants', []):
        variant_name = variant.get('variant')
        for amount in variant.get('amount_regions', []):
            if amount.get('zone') == 'article_zone':
                enriched = dict(amount)
                enriched['variant'] = variant_name
                out.append(enriched)
    return out


def _nearest_amount_for_cluster(cluster: dict[str, Any], amounts: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    cluster_box = cluster.get('cluster_box') or {}
    candidates = []
    for amount in amounts:
        amount_box = amount.get('box') or {}
        horizontal_gap = _box_left(amount_box) - _box_right(cluster_box)
        baseline = abs(_box_center_y(amount_box) - _box_center_y(cluster_box))
        if horizontal_gap < -40:
            continue
        if baseline > MAX_CLUSTER_AMOUNT_BASELINE_DISTANCE:
            continue
        candidates.append((baseline, max(0, horizontal_gap), amount))
    if not candidates:
        return None, 'no_article_zone_amount_right_of_cluster_within_tolerance'
    return sorted(candidates, key=lambda item: (item[0], item[1]))[0][2], 'vertical_proximity_left_alignment_right_amount'


def _existing_shadow_candidates(receipt_json: dict[str, Any]) -> list[dict[str, Any]]:
    shadow = receipt_json.get('metadata', {}).get('shadow_reconstruction_output', {})
    return shadow.get('generated_rows', []) or []


def build_ocr_structural_normalization(receipt_json: dict[str, Any]) -> dict[str, Any]:
    clusters_diag = receipt_json.get('metadata', {}).get('ocr_product_clusters', {})
    clusters = clusters_diag.get('clusters', []) or []
    stability = _stability_lookup(receipt_json)
    amount_regions = _article_amounts(receipt_json)
    normalized_groups = []
    rejected_groups = []

    for index, cluster in enumerate(clusters, start=1):
        lines = [str(line) for line in cluster.get('cluster_text_lines', [])]
        normalized_text = ' '.join(line.strip() for line in lines if line and not _is_noise_text(line))
        cluster_box = cluster.get('cluster_box')
        amount, amount_reason = _nearest_amount_for_cluster(cluster, amount_regions)
        confidence = _structural_confidence(cluster, amount, stability)
        source_lines = []
        for raw in cluster.get('cluster_raw_lines', []) or []:
            # No line numbers are available in current cluster structure; keep raw text as trace.
            pass

        if not normalized_text:
            rejected_groups.append({
                'group_id': f'group_{index:03d}',
                'source_line_numbers': [],
                'cluster_id': cluster.get('cluster_id'),
                'cluster_text_lines': lines,
                'reject_reason': 'empty_or_noise_only_product_cluster',
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })
            continue

        if any(token in _norm(normalized_text) for token in BLOCKED_ZONE_REASONS):
            rejected_groups.append({
                'group_id': f'group_{index:03d}',
                'source_line_numbers': [],
                'cluster_id': cluster.get('cluster_id'),
                'cluster_text_lines': lines,
                'reject_reason': 'payment_or_total_zone_noise',
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })
            continue

        group_type = 'multi_line_product_amount_group' if amount else 'multi_line_product_without_amount_group'
        if len(lines) <= 1:
            group_type = 'single_line_product_amount_group' if amount else 'single_line_product_without_amount_group'

        group = {
            'group_id': f'group_{index:03d}',
            'cluster_id': cluster.get('cluster_id'),
            'source_line_numbers': [],
            'cluster_box': cluster_box,
            'normalized_text': normalized_text,
            'cluster_text_lines': lines,
            'linked_amount_text': amount.get('text') if amount else '',
            'linked_amounts': amount.get('amounts', []) if amount else [],
            'linked_amount_box': amount.get('box') if amount else None,
            'linked_amount_variant': amount.get('variant') if amount else '',
            'group_type': group_type,
            'confidence_score': confidence,
            'normalization_reason': amount_reason,
            'broken_word_join_hints': _broken_word_join_hints(lines),
            'diagnostic_only': True,
            'reconstruction_applied': False,
        }

        if confidence >= MIN_GROUP_CONFIDENCE:
            normalized_groups.append(group)
        else:
            rejected_groups.append({**group, 'reject_reason': 'confidence_below_structural_group_threshold'})

    shadow_rows = _existing_shadow_candidates(receipt_json)
    for shadow in shadow_rows:
        normalized_groups.append({
            'group_id': f'shadow_{len(normalized_groups) + 1:03d}',
            'cluster_id': shadow.get('cluster_id'),
            'source_line_numbers': [],
            'normalized_text': shadow.get('product_name'),
            'linked_amount_text': shadow.get('amount_text'),
            'linked_amounts': shadow.get('amounts', []),
            'group_type': 'shadow_low_risk_product_amount_group',
            'confidence_score': shadow.get('reliability_score'),
            'normalization_reason': 'existing_low_risk_shadow_reconstruction_candidate',
            'diagnostic_only': True,
            'reconstruction_applied': False,
        })

    return {
        'diagnostic_scope': 'ocr_structural_line_group_normalization',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'normalized_group_count': len(normalized_groups),
        'rejected_group_count': len(rejected_groups),
        'rules': {
            'max_cluster_amount_baseline_distance': MAX_CLUSTER_AMOUNT_BASELINE_DISTANCE,
            'min_group_confidence': MIN_GROUP_CONFIDENCE,
            'parser_input_changed': False,
            'csv_output_changed': False,
        },
        'normalized_line_groups': normalized_groups,
        'rejected_groups': rejected_groups,
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('ocr_structural_normalization', {})

    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_ocr_structural_normalization(payload)
        payload.setdefault('metadata', {})['ocr_structural_normalization'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['ocr_structural_normalization'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1

    summary['schema_version'] = 'receipt-ocr-benchmark-v30-ocr-structural-normalization'
    summary['ocr_structural_normalization_processed_receipts'] = processed
    summary['ocr_structural_normalization_skipped_receipts'] = skipped
    summary['ocr_structural_normalization_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] OCR structural normalization diagnostics added for {processed} receipts; skipped={skipped}')


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
