from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image

from add_ocr_region_diagnostics import build_region_diagnostics

AMOUNT_PATTERN = re.compile(r'(?<!\d)(-?\d+[\.,]\d{2})(?!\d)')
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}
PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}


def _pil_to_cv(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(image.convert('RGB')), cv2.COLOR_RGB2BGR)


def _cv_to_pil(image: np.ndarray) -> Image.Image:
    if len(image.shape) == 2:
        return Image.fromarray(image)
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


def _variant_images(image_path: Path) -> list[tuple[str, Image.Image]]:
    source = Image.open(image_path).convert('RGB')
    cv_image = _pil_to_cv(source)
    gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

    variants: list[tuple[str, Image.Image]] = [
        ('original', source),
        ('grayscale', Image.fromarray(gray)),
    ]

    contrast = cv2.convertScaleAbs(gray, alpha=1.45, beta=8)
    variants.append(('contrast', Image.fromarray(contrast)))

    threshold = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        11,
    )
    variants.append(('threshold', Image.fromarray(threshold)))

    sharpen_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpen = cv2.filter2D(gray, -1, sharpen_kernel)
    variants.append(('sharpen', Image.fromarray(sharpen)))

    scale_up = cv2.resize(gray, None, fx=1.75, fy=1.75, interpolation=cv2.INTER_CUBIC)
    variants.append(('scale_up_175', Image.fromarray(scale_up)))

    contrast_scale = cv2.resize(contrast, None, fx=1.75, fy=1.75, interpolation=cv2.INTER_CUBIC)
    variants.append(('contrast_scale_up_175', Image.fromarray(contrast_scale)))

    return variants


def _write_temp_variant(temp_dir: Path, source_image_path: Path, variant_name: str, image: Image.Image) -> Path:
    temp_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r'[^A-Za-z0-9_.-]+', '_', source_image_path.stem)
    output_path = temp_dir / f'{safe_stem}__{variant_name}.png'
    image.save(output_path)
    return output_path


def build_preprocessing_variant_diagnostics(image_path: Path, receipt_json: dict, lang: str, temp_dir: Path) -> dict[str, object]:
    variant_results = []
    best_variant = None

    for variant_name, variant_image in _variant_images(image_path):
        variant_path = _write_temp_variant(temp_dir, image_path, variant_name, variant_image)
        try:
            region_diag = build_region_diagnostics(variant_path, receipt_json, lang)
            result = {
                'variant': variant_name,
                'ocr_region_count': region_diag.get('ocr_region_count', 0),
                'amount_region_count': region_diag.get('amount_region_count', 0),
                'candidate_region_link_count': region_diag.get('candidate_region_link_count', 0),
                'candidate_region_links': region_diag.get('candidate_region_links', []),
                'diagnostic_only': True,
                'reconstruction_applied': False,
                'image_written': str(variant_path).replace('\\', '/'),
            }
        except Exception as exc:  # diagnostics must not change parser behavior
            result = {
                'variant': variant_name,
                'ocr_region_count': 0,
                'amount_region_count': 0,
                'candidate_region_link_count': 0,
                'candidate_region_links': [],
                'diagnostic_only': True,
                'reconstruction_applied': False,
                'error': str(exc),
                'image_written': str(variant_path).replace('\\', '/'),
            }
        variant_results.append(result)

        if best_variant is None:
            best_variant = result
        else:
            best_key = (
                int(best_variant.get('candidate_region_link_count', 0)),
                int(best_variant.get('amount_region_count', 0)),
                int(best_variant.get('ocr_region_count', 0)),
            )
            current_key = (
                int(result.get('candidate_region_link_count', 0)),
                int(result.get('amount_region_count', 0)),
                int(result.get('ocr_region_count', 0)),
            )
            if current_key > best_key:
                best_variant = result

    return {
        'diagnostic_scope': 'image_preprocessing_variant_ocr_region_diagnostics',
        'diagnostic_only': True,
        'reconstruction_applied': False,
        'image_file': image_path.name,
        'variant_count': len(variant_results),
        'best_variant': {
            'variant': best_variant.get('variant') if best_variant else '',
            'ocr_region_count': best_variant.get('ocr_region_count') if best_variant else 0,
            'amount_region_count': best_variant.get('amount_region_count') if best_variant else 0,
            'candidate_region_link_count': best_variant.get('candidate_region_link_count') if best_variant else 0,
        },
        'variants': variant_results,
    }


def _image_by_stem(input_dir: Path) -> dict[str, Path]:
    return {path.stem: path for path in input_dir.iterdir() if path.suffix.lower() in SUPPORTED_EXTENSIONS}


def _should_run_for_image(image_path: Path) -> bool:
    return image_path.suffix.lower() in PHOTO_EXTENSIONS


def update_run(input_dir: Path, output_dir: Path, lang: str) -> None:
    json_dir = output_dir / 'json'
    if not json_dir.exists():
        raise FileNotFoundError(f'JSON output directory not found: {json_dir}')

    image_lookup = _image_by_stem(input_dir)
    summary_path = output_dir / 'benchmark_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
    summary.setdefault('preprocessing_variant_diagnostics', {})
    temp_dir = output_dir / 'debug_images' / 'preprocessing_variants'

    processed = 0
    skipped = 0
    for json_path in sorted(json_dir.glob('*.json')):
        image_path = image_lookup.get(json_path.stem)
        if image_path is None:
            continue
        payload = json.loads(json_path.read_text(encoding='utf-8'))
        if not _should_run_for_image(image_path):
            diagnostics = {
                'diagnostic_scope': 'image_preprocessing_variant_ocr_region_diagnostics',
                'diagnostic_only': True,
                'reconstruction_applied': False,
                'image_file': image_path.name,
                'variant_count': 0,
                'best_variant': {},
                'variants': [],
                'skip_reason': 'non_photo_input_extension',
            }
            skipped += 1
        else:
            diagnostics = build_preprocessing_variant_diagnostics(image_path, payload, lang, temp_dir)
            processed += 1

        payload.setdefault('metadata', {})['preprocessing_variant_diagnostics'] = diagnostics
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        summary['preprocessing_variant_diagnostics'][payload.get('metadata', {}).get('source_file', image_path.name)] = diagnostics

    current_schema = str(summary.get('schema_version', 'receipt-ocr-benchmark'))
    if 'v16-ocr-region-diagnostics' in current_schema:
        summary['schema_version'] = current_schema.replace('v16-ocr-region-diagnostics', 'v17-preprocessing-variant-diagnostics')
    elif 'v15-name-amount-link-diagnostics' in current_schema:
        summary['schema_version'] = current_schema.replace('v15-name-amount-link-diagnostics', 'v17-preprocessing-variant-diagnostics')
    else:
        summary['schema_version'] = 'receipt-ocr-benchmark-v17-preprocessing-variant-diagnostics'
    summary['preprocessing_variant_diagnostics_processed_receipts'] = processed
    summary['preprocessing_variant_diagnostics_skipped_receipts'] = skipped
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[OK] Preprocessing variant diagnostics added for {processed} receipts; skipped={skipped}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='input_receipts')
    parser.add_argument('--output', required=True)
    parser.add_argument('--lang', default='nld+eng')
    args = parser.parse_args()
    update_run(Path(args.input), Path(args.output), args.lang)


if __name__ == '__main__':
    main()
