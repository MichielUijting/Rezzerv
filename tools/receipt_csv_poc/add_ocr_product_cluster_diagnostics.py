from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from add_amount_region_zone_diagnostics import _image_by_stem, _should_run_for_image

DEFAULT_TARGETS = {
    'AH foto 2',
    'Aldi foto 2',
    'Plus foto 2',
    'plus foto 1',
}
MAX_CLUSTER_VERTICAL_GAP_PX = 42
MAX_LEFT_ALIGNMENT_DELTA_PX = 90
MIN_HORIZONTAL_OVERLAP_PERCENTAGE = 12
MAX_AMOUNT_CLUSTER_BASELINE_DISTANCE_PX = 58
MIN_AMOUNT_CLUSTER_GAP_PX = -30
MAX_AMOUNT_CLUSTER_GAP_PX = 820


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


def _norm(value: str) -> str:
    value = re.sub(r'[^a-z0-9à-ÿ]+', ' ', str(value or '').lower())
    return re.sub(r'\s+', ' ', value).strip()


def _is_non_product_text(text: str) -> bool:
    normalized = _norm(text)
    blocked = (
        'totaal', 'subtotaal', 'betaal', 'pin', 'kaart', 'btw', 'wisselgeld',
        'zegel', 'campagne', 'pluspunt', 'spaarkaart', 'omschrijving', 'prijs',
        'bedrag', 'aantal', 'tel', 'terminal', 'merchant', 'klantticket',
        'contactless', 'bonus box', 'datum', 'kassa', 'bon', 'chip', 'waarvan',
        'albert heijn', 'polenplein',
    )
    return any(word in normalized for word in blocked) or len(normalized) < 3


def _left(box: dict) -> int:
    return int(box.get('left', 0))


def _right(box: dict) -> int:
    return int(box.get('right', int(box.get('left', 0)) + int(box.get('width', 0))))


def _top(box: dict) -> int:
    return int(box.get('top', 0))


def _bottom(box: dict) -> int:
    return int(box.get('bottom', int(box.get('top', 0)) + int(box.get('height', 0))))


def _center_y(box: dict) -> int:
    return int(box.get('center_y', (_top(box) + _bottom(box)) // 2))


def _height(box: dict) -> int:
    return max(1, _bottom(box) - _top(box))


def _horizontal_overlap_percentage(a: dict, b: dict) -> int:
    overlap = max(0, min(_right(a), _right(b)) - max(_left(a), _left(b)))
    reference_width = max(1, min(_right(a) - _left(a), _right(b) - _left(b)))
    return int(round((overlap / reference_width) * 100))


def _union_box(boxes: list[dict]) -> dict:
    left = min(_left(box) for box in boxes)
    top = min(_top(box) for box in boxes)
    right = max(_right(box) for box in boxes)
    bottom = max(_bottom(box) for box in boxes)
    return {
        'left': left,
        'top': top,
        'width': right - left,
        'height': bottom - top,
        'right': right,
        'bottom': bottom,
        'center_x': int((left + right) / 2),
        'center_y': int((top + bottom) / 2),
    }


def _extract_product_regions(receipt_json: dict) -> list[dict]:
    ocr_diag = receipt_json.get('metadata', {}).get('ocr_region_amount_diagnostics', {})
    regions: list[dict] = []
    for item in ocr_diag.get('orphan_product_name_region_diagnostics', []):
        text = item.get('name_region_text') or item.get('product_name_raw_line') or ''
        box = item.get('name_region_box')
        if not box or _is_non_product_text(text):
            continue
        regions.append({
            'text': text,
            'raw_line': item.get('product_name_raw_line') or text,
            'box': box,
            'confidence': item.get('mean_confidence'),
        })
    return sorted(regions, key=lambda region: (_top(region['box']), _left(region['box'])))


def _can_join(prev: dict, current: dict) -> tuple[bool, str, dict[str, int]]:
    prev_box = prev['box']
    current_box = current['box']
    vertical_gap = _top(current_box) - _bottom(prev_box)
    left_delta = abs(_left(current_box) - _left(prev_box))
    overlap = _horizontal_overlap_percentage(prev_box, current_box)
    height_delta = abs(_height(current_box) - _height(prev_box))
    metrics = {
        'vertical_gap_px': vertical_gap,
        'left_alignment_delta_px': left_delta,
        'horizontal_overlap_percentage': overlap,
        'height_delta_px': height_delta,
    }

    if vertical_gap < -MAX_CLUSTER_VERTICAL_GAP_PX:
        return False, 'current_region_above_or_overlapping_too_much', metrics
    if vertical_gap > MAX_CLUSTER_VERTICAL_GAP_PX:
        return False, 'vertical_gap_too_large', metrics
    if left_delta <= MAX_LEFT_ALIGNMENT_DELTA_PX:
        return True, 'left_alignment_within_tolerance', metrics
    if overlap >= MIN_HORIZONTAL_OVERLAP_PERCENTAGE:
        return True, 'horizontal_overlap_within_tolerance', metrics
    return False, 'left_alignment_and_horizontal_overlap_insufficient', metrics


def _cluster_product_regions(product_regions: list[dict]) -> list[dict]:
    clusters: list[list[dict]] = []
    current: list[dict] = []

    for region in product_regions:
        if not current:
            current = [region]
            continue
        can_join, _reason, _metrics = _can_join(current[-1], region)
        if can_join:
            current.append(region)
        else:
            clusters.append(current)
            current = [region]
    if current:
        clusters.append(current)

    output = []
    for index, cluster in enumerate(clusters, start=1):
        boxes = [item['box'] for item in cluster]
        confidences = [float(item['confidence']) for item in cluster if item.get('confidence') is not None]
        cluster_box = _union_box(boxes)
        output.append({
            'cluster_id': f'cluster_{index:03d}',
            'cluster_box': cluster_box,
            'cluster_text_lines': [item['text'] for item in cluster],
            'cluster_raw_lines': [item['raw_line'] for item in cluster],
            'cluster_confidence': round(sum(confidences) / len(confidences), 2) if confidences else None,
            'region_count': len(cluster),
        })
    return output


def _iter_article_amount_regions(receipt_json: dict) -> list[dict]:
    zone_diag = receipt_json.get('metadata', {}).get('amount_region_zone_diagnostics', {})
    amount_regions: list[dict] = []
    for variant in zone_diag.get('variants', []):
        variant_name = variant.get('variant')
        for amount_region in variant.get('amount_regions', []):
            if amount_region.get('zone') != 'article_zone':
                continue
            enriched = dict(amount_region)
            enriched['variant'] = variant_name
            amount_regions.append(enriched)
    return amount_regions


def _evaluate_cluster_amount(cluster: dict, amount_region: dict) -> dict[str, object]:
    cluster_box = cluster['cluster_box']
    amount_box = amount_region.get('box') or {}
    baseline_distance = abs(_center_y(cluster_box) - _center_y(amount_box))
    horizontal_gap = _left(amount_box) - _right(cluster_box)
    vertical_overlap = max(0, min(_bottom(cluster_box), _bottom(amount_box)) - max(_top(cluster_box), _top(amount_box)))

    if MIN_AMOUNT_CLUSTER_GAP_PX <= horizontal_gap <= MAX_AMOUNT_CLUSTER_GAP_PX and baseline_distance <= MAX_AMOUNT_CLUSTER_BASELINE_DISTANCE_PX:
        validation = 'cluster_alignment_candidate'
        reason = 'amount_right_of_product_cluster_with_acceptable_baseline_distance'
    elif horizontal_gap < MIN_AMOUNT_CLUSTER_GAP_PX:
        validation = 'rejected_cluster_candidate'
        reason = 'amount_not_right_of_product_cluster'
    elif horizontal_gap > MAX_AMOUNT_CLUSTER_GAP_PX:
        validation = 'rejected_cluster_candidate'
        reason = 'amount_too_far_right_from_product_cluster'
    else:
        validation = 'rejected_cluster_candidate'
        reason = 'baseline_distance_too_large_for_product_cluster'

    return {
        'variant': amount_region.get('variant'),
        'amount_text': amount_region.get('text'),
        'amounts': amount_region.get('amounts', []),
        'amount_box': amount_box,
        'amount_mean_confidence': amount_region.get('mean_confidence'),
        'validation': validation,
        'reason': reason,
        'baseline_distance_pixels': baseline_distance,
        'horizontal_gap_pixels': horizontal_gap,
        'vertical_overlap_pixels': vertical_overlap,
        'diagnostic_only': True,
    }


def build_ocr_product_clusters(receipt_json: dict) -> dict[str, object]:
    product_regions = _extract_product_regions(receipt_json)
    clusters = _cluster_product_regions(product_regions)
    article_amounts = _iter_article_amount_regions(receipt_json)

    for cluster in clusters:
        linked = []
        rejected = []
        for amount_region in article_amounts:
            result = _evaluate_cluster_amount(cluster, amount_region)
            if result['validation'] == 'cluster_alignment_candidate':
                linked.append(result)
            else:
                rejected.append(result)
        cluster['linked_amount_candidates'] = linked
        cluster['rejected_amount_candidates'] = rejected[:10]

    linked_count = sum(len(cluster.get('linked_amount_candidates', [])) for cluster in clusters)
    return {
        'diagnostic_scope': 'ocr_product_line_cluster_diagnostics',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'cluster_count': len(clusters),
        'linked_amount_candidate_count': linked_count,
        'product_region_count': len(product_regions),
        'article_zone_amount_count': len(article_amounts),
        'limits': {
            'max_cluster_vertical_gap_px': MAX_CLUSTER_VERTICAL_GAP_PX,
            'max_left_alignment_delta_px': MAX_LEFT_ALIGNMENT_DELTA_PX,
            'min_horizontal_overlap_percentage': MIN_HORIZONTAL_OVERLAP_PERCENTAGE,
            'max_amount_cluster_baseline_distance_px': MAX_AMOUNT_CLUSTER_BASELINE_DISTANCE_PX,
            'min_amount_cluster_gap_px': MIN_AMOUNT_CLUSTER_GAP_PX,
            'max_amount_cluster_gap_px': MAX_AMOUNT_CLUSTER_GAP_PX,
        },
        'clusters': clusters,
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('ocr_product_clusters', {})

    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_ocr_product_clusters(payload)
        payload.setdefault('metadata', {})['ocr_product_clusters'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['ocr_product_clusters'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1

    summary['schema_version'] = 'receipt-ocr-benchmark-v21-product-cluster-diagnostics'
    summary['ocr_product_cluster_diagnostics_processed_receipts'] = processed
    summary['ocr_product_cluster_diagnostics_skipped_receipts'] = skipped
    summary['ocr_product_cluster_diagnostics_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] OCR product cluster diagnostics added for {processed} receipts; skipped={skipped}')


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
