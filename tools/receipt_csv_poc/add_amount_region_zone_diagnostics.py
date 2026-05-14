from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image

from add_ocr_region_diagnostics import extract_ocr_regions
from add_preprocessing_variant_diagnostics import _variant_images, _write_temp_variant

SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}
PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}
ZONE_KEYWORDS = {
    'total_zone': ('totaal', 'subtotaal', 'te betalen'),
    'payment_zone': ('pin', 'pinnen', 'betaling', 'betaald', 'kaart', 'visa', 'contactless', 'wisselgeld'),
    'vat_zone': ('btw', 'biw', 'vat'),
    'header_zone': ('omschrijving', 'prijs', 'bedrag', 'aantal'),
}


def _normalize_text(value: str) -> str:
    return re.sub(r'\s+', ' ', str(value or '').lower()).strip()


def _image_by_stem(input_dir: Path) -> dict[str, Path]:
    return {path.stem: path for path in input_dir.iterdir() if path.suffix.lower() in SUPPORTED_EXTENSIONS}


def _should_run_for_image(image_path: Path) -> bool:
    return image_path.suffix.lower() in PHOTO_EXTENSIONS


def _variant_factor(variant_name: str) -> float:
    return 1.75 if 'scale_up_175' in variant_name else 1.0


def _scaled_y_from_line_region(line_region: dict | None, factor: float) -> int | None:
    if not line_region:
        return None
    box = line_region.get('box') or {}
    center_y = box.get('center_y')
    if center_y is None:
        return None
    return int(round(float(center_y) * factor))


def _find_region_for_text(text: str, regions: list[dict]) -> dict | None:
    target = _normalize_text(text)
    if not target:
        return None
    target_tokens = [token for token in re.sub(r'[^a-z0-9à-ÿ]+', ' ', target).split(' ') if len(token) >= 2]
    if not target_tokens:
        return None

    best_region = None
    best_score = 0
    for region in regions:
        region_text = re.sub(r'[^a-z0-9à-ÿ]+', ' ', _normalize_text(region.get('text', '')))
        score = sum(1 for token in target_tokens if token in region_text)
        if target in region_text:
            score += len(target_tokens)
        if score > best_score:
            best_score = score
            best_region = region
    return best_region if best_score > 0 else None


def _zone_by_keyword(text: str) -> tuple[str | None, str | None]:
    normalized = _normalize_text(text)
    for zone, keywords in ZONE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in normalized:
                return zone, f'amount_region_text_matches_{zone}_keyword:{keyword}'
    return None, None


def _build_zone_context(receipt_json: dict, regions: list[dict], variant_name: str) -> dict:
    factor = _variant_factor(variant_name)
    rescue = receipt_json.get('metadata', {}).get('product_block_rescue_diagnostics', {})
    orphan_names = rescue.get('orphan_product_name_lines') or []
    before_stop_names = []
    for orphan in orphan_names:
        stop_line_no = rescue.get('stop_line_no')
        line_no = int(orphan.get('line_no') or 0)
        if stop_line_no is not None and line_no >= int(stop_line_no):
            continue
        region = _find_region_for_text(str(orphan.get('raw_line') or ''), regions)
        if region:
            before_stop_names.append(region)

    name_tops = [int(region['box']['top']) for region in before_stop_names if region.get('box')]
    name_bottoms = [int(region['box']['bottom']) for region in before_stop_names if region.get('box')]
    name_rights = [int(region['box']['right']) for region in before_stop_names if region.get('box')]

    article_top = min(name_tops) - int(round(18 * factor)) if name_tops else None
    article_bottom = max(name_bottoms) + int(round(50 * factor)) if name_bottoms else None
    product_right_edge = max(name_rights) if name_rights else None

    stop_region = None
    stop_line_no = rescue.get('stop_line_no')
    if stop_line_no is not None:
        for line in receipt_json.get('classified_lines', []):
            if int(line.get('line_no') or 0) == int(stop_line_no):
                stop_region = _find_region_for_text(str(line.get('raw_line') or ''), regions)
                break
    stop_y = _scaled_y_from_line_region(stop_region, 1.0) if stop_region else None

    if stop_y is not None and article_bottom is not None:
        article_bottom = min(article_bottom, stop_y - int(round(8 * factor)))

    return {
        'variant_factor': factor,
        'article_top': article_top,
        'article_bottom': article_bottom,
        'product_right_edge': product_right_edge,
        'stop_y': stop_y,
        'matched_product_name_region_count': len(before_stop_names),
    }


def classify_amount_region(region: dict, context: dict) -> tuple[str, str]:
    text_zone, text_reason = _zone_by_keyword(str(region.get('text') or ''))
    if text_zone:
        return text_zone, text_reason or 'keyword_zone_match'

    box = region.get('box') or {}
    center_y = int(box.get('center_y', 0))
    left = int(box.get('left', 0))
    article_top = context.get('article_top')
    article_bottom = context.get('article_bottom')
    product_right_edge = context.get('product_right_edge')
    stop_y = context.get('stop_y')

    if article_top is not None and center_y < int(article_top):
        return 'header_zone', 'amount_region_above_inferred_article_zone'
    if stop_y is not None and center_y >= int(stop_y):
        return 'total_zone', 'amount_region_at_or_after_first_total_payment_vat_stopline'
    if article_top is not None and article_bottom is not None and int(article_top) <= center_y <= int(article_bottom):
        if product_right_edge is None or left >= int(product_right_edge) - 25:
            return 'article_zone', 'inside_inferred_article_zone_and_right_of_product_block'
        return 'article_zone', 'inside_inferred_article_zone'
    return 'unknown_zone', 'outside_inferred_article_zone_without_keyword_match'


def build_amount_region_zone_diagnostics(image_path: Path, receipt_json: dict, lang: str, temp_dir: Path) -> dict[str, object]:
    variants = []
    for variant_name, variant_image in _variant_images(image_path):
        variant_path = _write_temp_variant(temp_dir, image_path, variant_name, variant_image)
        try:
            regions = extract_ocr_regions(variant_path, lang)
            amount_regions = [region for region in regions if region.get('amounts')]
            context = _build_zone_context(receipt_json, regions, variant_name)
            classified_amounts = []
            article_count = 0
            for region in amount_regions:
                zone, reason = classify_amount_region(region, context)
                if zone == 'article_zone':
                    article_count += 1
                classified_amounts.append({
                    'text': region.get('text'),
                    'amounts': region.get('amounts', []),
                    'zone': zone,
                    'box': region.get('box'),
                    'zone_reason': reason,
                    'region_key': region.get('region_key'),
                    'mean_confidence': region.get('mean_confidence'),
                })
            variants.append({
                'variant': variant_name,
                'amount_region_count': len(amount_regions),
                'article_zone_amount_count': article_count,
                'non_article_zone_amount_count': len(amount_regions) - article_count,
                'amount_regions': classified_amounts,
                'zone_context': context,
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })
        except Exception as exc:
            variants.append({
                'variant': variant_name,
                'amount_region_count': 0,
                'article_zone_amount_count': 0,
                'non_article_zone_amount_count': 0,
                'amount_regions': [],
                'error': str(exc),
                'diagnostic_only': True,
                'reconstruction_applied': False,
            })

    best_article_variant = max(
        variants,
        key=lambda item: (
            int(item.get('article_zone_amount_count', 0)),
            int(item.get('amount_region_count', 0)),
        ),
        default={},
    )
    return {
        'diagnostic_scope': 'amount_region_zone_classification_by_preprocessing_variant',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'image_file': image_path.name,
        'best_article_zone_variant': {
            'variant': best_article_variant.get('variant', ''),
            'amount_region_count': best_article_variant.get('amount_region_count', 0),
            'article_zone_amount_count': best_article_variant.get('article_zone_amount_count', 0),
            'non_article_zone_amount_count': best_article_variant.get('non_article_zone_amount_count', 0),
        },
        'variants': variants,
    }


def update_run(input_dir: Path, output_dir: Path, lang: str) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('amount_region_zone_diagnostics', {})
    temp_dir = output_dir / 'debug_images' / 'zone_variants'

    processed = 0
    skipped = 0
    for json_path in sorted(json_dir.glob('*.json')):
        image_path = image_lookup.get(json_path.stem)
        if image_path is None:
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        if not _should_run_for_image(image_path):
            diagnostics = {
                'diagnostic_scope': 'amount_region_zone_classification_by_preprocessing_variant',
                'diagnostic_only': True,
                'reconstruction_applied': False,
                'image_file': image_path.name,
                'best_article_zone_variant': {},
                'variants': [],
                'skip_reason': 'non_photo_input_extension',
            }
            skipped += 1
        else:
            diagnostics = build_amount_region_zone_diagnostics(image_path, payload, lang, temp_dir)
            processed += 1

        payload.setdefault('metadata', {})['amount_region_zone_diagnostics'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['amount_region_zone_diagnostics'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics

    summary['schema_version'] = 'receipt-ocr-benchmark-v18-amount-region-zone-diagnostics'
    summary['amount_region_zone_diagnostics_processed_receipts'] = processed
    summary['amount_region_zone_diagnostics_skipped_receipts'] = skipped
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Amount region zone diagnostics added for {processed} receipts; skipped={skipped}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='input_receipts')
    parser.add_argument('--output', required=True)
    parser.add_argument('--lang', default='nld+eng')
    args = parser.parse_args()
    update_run(Path(args.input), Path(args.output), args.lang)


if __name__ == '__main__':
    main()
