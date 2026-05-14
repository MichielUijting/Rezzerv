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
STRICT_MAX_BASELINE_DISTANCE_PX = 18
RELAXED_MAX_BASELINE_DISTANCE_PX = 52
STRICT_MIN_VERTICAL_OVERLAP_PERCENTAGE = 45
RELAXED_MIN_VERTICAL_OVERLAP_PERCENTAGE = 12
MAX_LEFT_GAP_PX = 760
MIN_LEFT_GAP_PX = -25
MULTILINE_MAX_VERTICAL_GAP_PX = 34


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


def _norm(value: str) -> str:
    value = re.sub(r'[^a-z0-9à-ÿ]+', ' ', str(value or '').lower())
    return re.sub(r'\s+', ' ', value).strip()


def _is_non_product_name(text: str) -> bool:
    normalized = _norm(text)
    blocked = (
        'totaal', 'subtotaal', 'betaal', 'pin', 'kaart', 'btw', 'wisselgeld',
        'zegel', 'campagne', 'pluspunt', 'spaarkaart', 'omschrijving', 'prijs',
        'bedrag', 'aantal', 'tel', 'terminal', 'merchant', 'klantticket',
        'contactless', 'bonus box', 'datum', 'kassa', 'bon', 'chip',
    )
    return any(word in normalized for word in blocked) or len(normalized) < 3


def _center_y(box: dict) -> int:
    return int(box.get('center_y', int(box.get('top', 0)) + int(box.get('height', 0)) // 2))


def _right(box: dict) -> int:
    return int(box.get('right', int(box.get('left', 0)) + int(box.get('width', 0))))


def _left(box: dict) -> int:
    return int(box.get('left', 0))


def _top(box: dict) -> int:
    return int(box.get('top', 0))


def _bottom(box: dict) -> int:
    return int(box.get('bottom', int(box.get('top', 0)) + int(box.get('height', 0))))


def _vertical_overlap_percentage(a: dict, b: dict) -> int:
    overlap = max(0, min(_bottom(a), _bottom(b)) - max(_top(a), _top(b)))
    reference_height = max(1, min(_bottom(a) - _top(a), _bottom(b) - _top(b)))
    return int(round((overlap / reference_height) * 100))


def _extract_product_regions(receipt_json: dict) -> list[dict]:
    ocr_diag = receipt_json.get('metadata', {}).get('ocr_region_amount_diagnostics', {})
    regions: list[dict] = []
    for item in ocr_diag.get('orphan_product_name_region_diagnostics', []):
        text = item.get('name_region_text') or item.get('product_name_raw_line') or ''
        box = item.get('name_region_box')
        if not box or _is_non_product_name(text):
            continue
        regions.append({
            'product_name_text': text,
            'product_name_raw_line': item.get('product_name_raw_line') or text,
            'box': box,
            'mean_confidence': item.get('mean_confidence'),
            'source': 'ocr_region_amount_diagnostics',
        })
    return regions


def _detect_multiline_product_candidate(product_region: dict, all_products: list[dict], amount_box: dict) -> dict[str, object]:
    product_box = product_region.get('box') or {}
    product_y = _center_y(product_box)
    amount_y = _center_y(amount_box)
    candidates = []
    for other in all_products:
        if other is product_region:
            continue
        other_box = other.get('box') or {}
        if abs(_center_y(other_box) - product_y) <= MULTILINE_MAX_VERTICAL_GAP_PX:
            if _left(other_box) <= _left(amount_box) and abs(_center_y(other_box) - amount_y) <= RELAXED_MAX_BASELINE_DISTANCE_PX:
                candidates.append({
                    'product_name_text': other.get('product_name_text'),
                    'box': other_box,
                    'vertical_gap_px': abs(_center_y(other_box) - product_y),
                })
    return {
        'multi_line_product_candidate': bool(candidates),
        'nearby_product_name_regions': candidates[:3],
    }


def _score_pair(product_region: dict, amount_region: dict, all_products: list[dict]) -> dict[str, object]:
    product_box = product_region.get('box') or {}
    amount_box = amount_region.get('box') or {}
    baseline_distance = abs(_center_y(product_box) - _center_y(amount_box))
    vertical_overlap = _vertical_overlap_percentage(product_box, amount_box)
    horizontal_gap = _left(amount_box) - _right(product_box)
    multiline = _detect_multiline_product_candidate(product_region, all_products, amount_box)

    score = 0
    if MIN_LEFT_GAP_PX <= horizontal_gap <= MAX_LEFT_GAP_PX:
        score += 35
    if vertical_overlap >= STRICT_MIN_VERTICAL_OVERLAP_PERCENTAGE:
        score += 35
    elif vertical_overlap >= RELAXED_MIN_VERTICAL_OVERLAP_PERCENTAGE:
        score += 20
    if baseline_distance <= STRICT_MAX_BASELINE_DISTANCE_PX:
        score += 25
    elif baseline_distance <= RELAXED_MAX_BASELINE_DISTANCE_PX:
        score += 15
    if multiline['multi_line_product_candidate']:
        score += 5

    if baseline_distance <= STRICT_MAX_BASELINE_DISTANCE_PX and vertical_overlap >= STRICT_MIN_VERTICAL_OVERLAP_PERCENTAGE and MIN_LEFT_GAP_PX <= horizontal_gap <= MAX_LEFT_GAP_PX:
        validation = 'strict_same_line_candidate'
        reason = 'same_visual_line_with_strong_vertical_overlap'
    elif baseline_distance <= RELAXED_MAX_BASELINE_DISTANCE_PX and vertical_overlap >= RELAXED_MIN_VERTICAL_OVERLAP_PERCENTAGE and MIN_LEFT_GAP_PX <= horizontal_gap <= MAX_LEFT_GAP_PX:
        validation = 'relaxed_visual_alignment_candidate'
        reason = 'nearby_left_product_with_partial_vertical_overlap'
    else:
        validation = 'rejected_candidate'
        if horizontal_gap < MIN_LEFT_GAP_PX:
            reason = 'amount_not_to_the_right_of_product_region'
        elif horizontal_gap > MAX_LEFT_GAP_PX:
            reason = 'amount_too_far_right_from_product_region'
        elif baseline_distance > RELAXED_MAX_BASELINE_DISTANCE_PX:
            reason = 'baseline_distance_too_large'
        else:
            reason = 'vertical_overlap_too_small'

    return {
        'product_name_text': product_region.get('product_name_text'),
        'product_name_raw_line': product_region.get('product_name_raw_line'),
        'product_name_box': product_box,
        'product_name_mean_confidence': product_region.get('mean_confidence'),
        'amount_text': amount_region.get('text'),
        'amounts': amount_region.get('amounts', []),
        'amount_box': amount_box,
        'amount_mean_confidence': amount_region.get('mean_confidence'),
        'nearest_left_product_region': product_region.get('product_name_text'),
        'vertical_overlap_percentage': vertical_overlap,
        'baseline_distance_pixels': baseline_distance,
        'horizontal_gap_pixels': horizontal_gap,
        'multi_line_product_candidate': multiline['multi_line_product_candidate'],
        'nearby_product_name_regions': multiline['nearby_product_name_regions'],
        'flexible_alignment_score': score,
        'validation': validation,
        'reason': reason,
        'diagnostic_only': True,
    }


def _nearest_left_products(amount_region: dict, product_regions: list[dict]) -> list[dict]:
    amount_box = amount_region.get('box') or {}
    left_candidates = []
    for product in product_regions:
        product_box = product.get('box') or {}
        horizontal_gap = _left(amount_box) - _right(product_box)
        if horizontal_gap >= MIN_LEFT_GAP_PX:
            left_candidates.append((abs(_center_y(product_box) - _center_y(amount_box)), abs(horizontal_gap), product))
    return [entry[2] for entry in sorted(left_candidates, key=lambda entry: (entry[0], entry[1]))[:5]]


def build_flexible_alignment_validation(receipt_json: dict) -> dict[str, object]:
    zone_diag = receipt_json.get('metadata', {}).get('amount_region_zone_diagnostics', {})
    product_regions = _extract_product_regions(receipt_json)
    variants_out = []

    for variant in zone_diag.get('variants', []):
        variant_name = str(variant.get('variant') or '')
        article_amounts = [region for region in variant.get('amount_regions', []) if region.get('zone') == 'article_zone']
        validated_pairs = []
        rejected_pairs = []

        for amount_region in article_amounts:
            candidate_products = _nearest_left_products(amount_region, product_regions)
            if not candidate_products:
                rejected_pairs.append({
                    'amount_text': amount_region.get('text'),
                    'amounts': amount_region.get('amounts', []),
                    'amount_box': amount_region.get('box'),
                    'amount_mean_confidence': amount_region.get('mean_confidence'),
                    'validation': 'rejected_candidate',
                    'reason': 'no_left_product_region_available',
                    'diagnostic_only': True,
                })
                continue
            scored = [_score_pair(product, amount_region, product_regions) for product in candidate_products]
            best = sorted(scored, key=lambda item: item.get('flexible_alignment_score', 0), reverse=True)[0]
            if best['validation'] in ('strict_same_line_candidate', 'relaxed_visual_alignment_candidate'):
                validated_pairs.append(best)
            else:
                rejected_pairs.append(best)

        variants_out.append({
            'variant': variant_name,
            'article_zone_amount_count': len(article_amounts),
            'validated_pair_count': len(validated_pairs),
            'rejected_pair_count': len(rejected_pairs),
            'validated_pairs': validated_pairs,
            'rejected_pairs': rejected_pairs,
            'diagnostic_only': True,
            'reconstruction_applied': False,
        })

    best_variant = max(
        variants_out,
        key=lambda item: (int(item.get('validated_pair_count', 0)), int(item.get('article_zone_amount_count', 0))),
        default={},
    )
    return {
        'diagnostic_scope': 'flexible_visual_alignment_for_article_zone_amounts',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'best_variant': {
            'variant': best_variant.get('variant', ''),
            'article_zone_amount_count': best_variant.get('article_zone_amount_count', 0),
            'validated_pair_count': best_variant.get('validated_pair_count', 0),
            'rejected_pair_count': best_variant.get('rejected_pair_count', 0),
        },
        'limits': {
            'strict_max_baseline_distance_px': STRICT_MAX_BASELINE_DISTANCE_PX,
            'relaxed_max_baseline_distance_px': RELAXED_MAX_BASELINE_DISTANCE_PX,
            'strict_min_vertical_overlap_percentage': STRICT_MIN_VERTICAL_OVERLAP_PERCENTAGE,
            'relaxed_min_vertical_overlap_percentage': RELAXED_MIN_VERTICAL_OVERLAP_PERCENTAGE,
            'min_left_gap_px': MIN_LEFT_GAP_PX,
            'max_left_gap_px': MAX_LEFT_GAP_PX,
        },
        'variants': variants_out,
    }


def update_targeted_run(input_dir: Path, output_dir: Path, targets: set[str]) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('flexible_alignment_validation', {})

    processed = 0
    skipped = 0
    for target in sorted(targets):
        json_path = json_dir / f'{target}.json'
        image_path = image_lookup.get(target)
        if image_path is None or not json_path.exists() or not _should_run_for_image(image_path):
            skipped += 1
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_flexible_alignment_validation(payload)
        payload.setdefault('metadata', {})['flexible_alignment_validation'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['flexible_alignment_validation'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1

    summary['schema_version'] = 'receipt-ocr-benchmark-v20-flexible-alignment-validation'
    summary['flexible_alignment_validation_processed_receipts'] = processed
    summary['flexible_alignment_validation_skipped_receipts'] = skipped
    summary['flexible_alignment_validation_targeted_only'] = True
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Flexible alignment validation added for {processed} receipts; skipped={skipped}')


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
