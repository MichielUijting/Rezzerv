from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pytesseract
from PIL import Image

AMOUNT_PATTERN = re.compile(r'(?<!\d)(-?\d+[\.,]\d{2})(?!\d)')
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}
MAX_VERTICAL_DISTANCE_PX = 28
MAX_NEARBY_VERTICAL_DISTANCE_PX = 60
MIN_RIGHT_GAP_PX = -10


def normalize_decimal(value: str) -> str:
    return value.replace(',', '.').strip()


def _box(left: int, top: int, width: int, height: int) -> dict[str, int]:
    return {
        'left': int(left),
        'top': int(top),
        'width': int(width),
        'height': int(height),
        'right': int(left + width),
        'bottom': int(top + height),
        'center_x': int(left + width / 2),
        'center_y': int(top + height / 2),
    }


def _union_box(boxes: list[dict[str, int]]) -> dict[str, int] | None:
    if not boxes:
        return None
    left = min(box['left'] for box in boxes)
    top = min(box['top'] for box in boxes)
    right = max(box['right'] for box in boxes)
    bottom = max(box['bottom'] for box in boxes)
    return _box(left, top, right - left, bottom - top)


def _line_key(data: dict, index: int) -> tuple[int, int, int, int]:
    return (
        int(data['page_num'][index]),
        int(data['block_num'][index]),
        int(data['par_num'][index]),
        int(data['line_num'][index]),
    )


def extract_ocr_regions(image_path: Path, lang: str) -> list[dict[str, object]]:
    data = pytesseract.image_to_data(Image.open(image_path), lang=lang, output_type=pytesseract.Output.DICT)
    grouped: dict[tuple[int, int, int, int], list[dict[str, object]]] = {}

    for index, text in enumerate(data.get('text', [])):
        word = str(text or '').strip()
        if not word:
            continue
        try:
            conf = float(data['conf'][index])
        except (ValueError, TypeError):
            conf = -1.0
        if conf < 0:
            continue
        word_box = _box(data['left'][index], data['top'][index], data['width'][index], data['height'][index])
        grouped.setdefault(_line_key(data, index), []).append({
            'text': word,
            'conf': conf,
            'box': word_box,
        })

    regions = []
    for key, words in grouped.items():
        words_sorted = sorted(words, key=lambda item: (item['box']['left'], item['box']['top']))
        text = ' '.join(str(item['text']) for item in words_sorted).strip()
        boxes = [item['box'] for item in words_sorted]
        line_box = _union_box(boxes)
        if not text or not line_box:
            continue
        amounts = [normalize_decimal(match) for match in AMOUNT_PATTERN.findall(text)]
        regions.append({
            'region_key': f'{key[0]}:{key[1]}:{key[2]}:{key[3]}',
            'text': text,
            'box': line_box,
            'amounts': amounts,
            'word_count': len(words_sorted),
            'mean_confidence': round(sum(float(item['conf']) for item in words_sorted) / len(words_sorted), 2),
            'words': words_sorted,
        })

    return sorted(regions, key=lambda item: (item['box']['top'], item['box']['left']))


def _normalize_for_match(value: str) -> str:
    value = value.lower()
    value = re.sub(r'[^a-z0-9à-ÿ]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def _find_name_region(product_name: str, regions: list[dict[str, object]]) -> tuple[dict[str, object] | None, str]:
    target = _normalize_for_match(product_name)
    if not target:
        return None, 'empty_product_name'

    target_tokens = [token for token in target.split(' ') if len(token) >= 2]
    if not target_tokens:
        return None, 'no_matchable_product_name_tokens'

    best_region = None
    best_score = 0
    for region in regions:
        region_text = _normalize_for_match(str(region.get('text', '')))
        if not region_text:
            continue
        score = sum(1 for token in target_tokens if token in region_text)
        if target in region_text:
            score += len(target_tokens)
        if score > best_score:
            best_score = score
            best_region = region

    if best_region is None or best_score == 0:
        return None, 'no_ocr_region_matches_product_name_text'
    return best_region, 'matched_by_normalized_text_tokens'


def _amount_regions(regions: list[dict[str, object]]) -> list[dict[str, object]]:
    return [region for region in regions if region.get('amounts')]


def _classify_region_relation(name_region: dict[str, object], amount_region: dict[str, object]) -> tuple[bool, str, dict[str, int]]:
    name_box = name_region['box']
    amount_box = amount_region['box']
    vertical_distance = abs(int(amount_box['center_y']) - int(name_box['center_y']))
    horizontal_gap = int(amount_box['left']) - int(name_box['right'])
    metrics = {
        'vertical_distance_px': vertical_distance,
        'horizontal_gap_px': horizontal_gap,
    }

    if vertical_distance <= MAX_VERTICAL_DISTANCE_PX and horizontal_gap >= MIN_RIGHT_GAP_PX:
        return True, 'amount_region_right_on_same_visual_line', metrics
    if vertical_distance <= MAX_NEARBY_VERTICAL_DISTANCE_PX and horizontal_gap >= MIN_RIGHT_GAP_PX:
        return True, 'amount_region_right_nearby_visual_line', metrics
    if horizontal_gap < MIN_RIGHT_GAP_PX:
        return False, 'amount_region_not_to_the_right_of_product_region', metrics
    return False, 'amount_region_too_far_vertically', metrics


def build_region_diagnostics(image_path: Path, receipt_json: dict, lang: str) -> dict[str, object]:
    regions = extract_ocr_regions(image_path, lang)
    amount_regions = _amount_regions(regions)
    rescue = receipt_json.get('metadata', {}).get('product_block_rescue_diagnostics', {})
    orphan_names = rescue.get('orphan_product_name_lines') or []
    stop_line_no = rescue.get('stop_line_no')

    name_diagnostics = []
    candidate_links = []

    for orphan in orphan_names:
        line_no = int(orphan.get('line_no', 0) or 0)
        raw_name = str(orphan.get('raw_line') or '')
        before_stop = stop_line_no is None or line_no < int(stop_line_no)
        if not before_stop:
            name_diagnostics.append({
                'product_name_line_no': line_no,
                'product_name_raw_line': raw_name,
                'name_region': None,
                'candidate_amount_regions': [],
                'reject_reason': 'product_name_line_in_or_after_total_payment_vat_zone',
            })
            continue

        name_region, match_reason = _find_name_region(raw_name, regions)
        if name_region is None:
            name_diagnostics.append({
                'product_name_line_no': line_no,
                'product_name_raw_line': raw_name,
                'name_region': None,
                'candidate_amount_regions': [],
                'reject_reason': match_reason,
            })
            continue

        candidates = []
        rejects = []
        for amount_region in amount_regions:
            accepted, reason, metrics = _classify_region_relation(name_region, amount_region)
            entry = {
                'amount_region_key': amount_region['region_key'],
                'amount_region_text': amount_region['text'],
                'amounts': amount_region['amounts'],
                'amount_region_box': amount_region['box'],
                **metrics,
                'diagnostic_reason' if accepted else 'reject_reason': reason,
            }
            if accepted:
                candidates.append(entry)
                candidate_links.append({
                    'product_name_line_no': line_no,
                    'product_name_raw_line': raw_name,
                    'name_region_key': name_region['region_key'],
                    'name_region_text': name_region['text'],
                    'name_region_box': name_region['box'],
                    **entry,
                    'diagnostic_only': True,
                })
            else:
                rejects.append(entry)

        name_diagnostics.append({
            'product_name_line_no': line_no,
            'product_name_raw_line': raw_name,
            'name_region_key': name_region['region_key'],
            'name_region_text': name_region['text'],
            'name_region_box': name_region['box'],
            'name_region_match_reason': match_reason,
            'candidate_amount_regions': candidates,
            'rejected_amount_regions': rejects[:10],
            'reject_reason': '' if candidates else 'no_amount_region_right_or_nearby_for_product_name_region',
        })

    return {
        'diagnostic_scope': 'tesseract_image_to_data_region_amount_diagnostics',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'image_file': image_path.name,
        'ocr_region_count': len(regions),
        'amount_region_count': len(amount_regions),
        'candidate_region_link_count': len(candidate_links),
        'candidate_region_links': candidate_links,
        'orphan_product_name_region_diagnostics': name_diagnostics,
        'limits': {
            'max_vertical_distance_px': MAX_VERTICAL_DISTANCE_PX,
            'max_nearby_vertical_distance_px': MAX_NEARBY_VERTICAL_DISTANCE_PX,
            'min_right_gap_px': MIN_RIGHT_GAP_PX,
        },
    }


def _image_by_stem(input_dir: Path) -> dict[str, Path]:
    return {path.stem: path for path in input_dir.iterdir() if path.suffix.lower() in SUPPORTED_EXTENSIONS}


def update_run(input_dir: Path, output_dir: Path, lang: str) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('ocr_region_amount_diagnostics', {})

    processed = 0
    for json_path in sorted(json_dir.glob('*.json')):
        image_path = image_lookup.get(json_path.stem)
        if image_path is None:
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        diagnostics = build_region_diagnostics(image_path, payload, lang)
        payload.setdefault('metadata', {})['ocr_region_amount_diagnostics'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['ocr_region_amount_diagnostics'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics
        processed += 1

    summary['schema_version'] = str(summary.get('schema_version', 'receipt-ocr-benchmark')).replace('v15-name-amount-link-diagnostics', 'v16-ocr-region-diagnostics')
    summary['ocr_region_diagnostics_processed_receipts'] = processed
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] OCR region diagnostics added for {processed} receipts')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='input_receipts')
    parser.add_argument('--output', required=True)
    parser.add_argument('--lang', default='nld+eng')
    args = parser.parse_args()
    update_run(Path(args.input), Path(args.output), args.lang)


if __name__ == '__main__':
    main()
