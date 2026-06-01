from __future__ import annotations

import io
import json
import math
import re
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
from sqlalchemy import text

from app.db import engine
from app.receipt_ingestion.service_parts.image_ocr_flow import _ocr_image_text_with_paddle
from app.services.receipt_service import _resolve_reparse_source_payload

ACTIVE_TARGET_RECEIPT_TABLE_IDS = (
    '7323172c2f364be5b53be9e11efb1ef4',  # plus foto 1.jpg
    '4ebdf7bf8a344093b6232ec5dd05b3c9',  # Plus foto 2.jpeg
)
OUTPUT_ROOT = Path('/tmp/rezzerv_preprocessing_diagnostics/r9_38b1a')
MAX_PREVIEW_SIDE = 1800
_AMOUNT_RE = re.compile(r'-?\d{1,6}(?:[\.,]\d{2})')
ARTICLE_HINT_RE = re.compile(r'[A-Za-zÀ-ÖØ-öø-ÿ]{3,}')


def _safe_name(value: str) -> str:
    return re.sub(r'[^a-zA-Z0-9._-]+', '_', str(value or 'receipt')).strip('_') or 'receipt'


def _image_stats(image: Image.Image) -> dict[str, Any]:
    gray = ImageOps.grayscale(image)
    hist = gray.histogram()
    total = sum(hist) or 1
    avg = sum(index * count for index, count in enumerate(hist)) / total
    variance = sum(((index - avg) ** 2) * count for index, count in enumerate(hist)) / total
    dark = sum(hist[:75]) / total
    bright = sum(hist[180:]) / total
    mid = 1.0 - dark - bright
    return {
        'width': image.width,
        'height': image.height,
        'mean_luminance': round(avg, 2),
        'luminance_stddev': round(math.sqrt(max(0.0, variance)), 2),
        'dark_pixel_ratio': round(dark, 4),
        'mid_pixel_ratio': round(mid, 4),
        'bright_pixel_ratio': round(bright, 4),
    }


def _resize_for_preview(image: Image.Image) -> Image.Image:
    width, height = image.size
    scale = min(1.0, MAX_PREVIEW_SIDE / max(width, height))
    if scale >= 1.0:
        return image.copy()
    return image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.LANCZOS)


def _save_preview(image: Image.Image, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    preview = _resize_for_preview(image.convert('RGB'))
    preview.save(path, format='JPEG', quality=92)
    return str(path)


def _image_to_jpeg_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert('RGB').save(buffer, format='JPEG', quality=95)
    return buffer.getvalue()


def _estimate_receipt_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Estimate receipt rectangle using only generic brightness/background contrast.

    Diagnostic-only. This does not alter runtime OCR and intentionally avoids
    filename/store-specific assumptions.
    """
    gray = ImageOps.grayscale(image)
    small_max = 900
    scale = min(1.0, small_max / max(gray.size))
    small = gray.resize((int(gray.width * scale), int(gray.height * scale)), Image.LANCZOS) if scale < 1.0 else gray
    blurred = small.filter(ImageFilter.GaussianBlur(radius=2))
    pixels = blurred.load()
    width, height = blurred.size

    hist = blurred.histogram()
    total = sum(hist) or 1
    cumulative = 0
    percentile_70 = 180
    for index, count in enumerate(hist):
        cumulative += count
        if cumulative / total >= 0.70:
            percentile_70 = index
            break
    threshold = max(120, min(235, percentile_70 + 8))

    xs: list[int] = []
    ys: list[int] = []
    for y in range(0, height, 2):
        for x in range(0, width, 2):
            if pixels[x, y] >= threshold:
                xs.append(x)
                ys.append(y)
    if len(xs) < 100:
        return None

    def pct(values: list[int], fraction: float) -> int:
        ordered = sorted(values)
        return ordered[min(len(ordered) - 1, max(0, int(len(ordered) * fraction)))]

    left = pct(xs, 0.02)
    right = pct(xs, 0.98)
    top = pct(ys, 0.02)
    bottom = pct(ys, 0.98)
    if right - left < width * 0.12 or bottom - top < height * 0.12:
        return None
    margin_x = max(4, int((right - left) * 0.025))
    margin_y = max(4, int((bottom - top) * 0.025))
    left = max(0, left - margin_x)
    right = min(width - 1, right + margin_x)
    top = max(0, top - margin_y)
    bottom = min(height - 1, bottom + margin_y)

    inv_scale = 1.0 / scale
    return (
        int(left * inv_scale),
        int(top * inv_scale),
        int(right * inv_scale),
        int(bottom * inv_scale),
    )


def _bbox_overlay(image: Image.Image, bbox: tuple[int, int, int, int] | None) -> Image.Image:
    overlay = image.convert('RGB').copy()
    draw = ImageDraw.Draw(overlay)
    if bbox is not None:
        draw.rectangle(bbox, outline=(255, 0, 0), width=max(4, int(max(image.size) / 450)))
    return overlay


def _contrast_score(image: Image.Image, bbox: tuple[int, int, int, int] | None) -> dict[str, Any]:
    gray = ImageOps.grayscale(image)
    if bbox is None:
        return {'receipt_background_contrast_score': None, 'reason': 'no_bbox_detected'}
    left, top, right, bottom = bbox
    receipt = gray.crop((left, top, right, bottom))
    receipt_mean = mean(list(receipt.resize((80, 160)).getdata()))

    samples: list[int] = []
    w, h = gray.size
    corner_boxes = [
        (0, 0, max(1, w // 5), max(1, h // 5)),
        (w - max(1, w // 5), 0, w, max(1, h // 5)),
        (0, h - max(1, h // 5), max(1, w // 5), h),
        (w - max(1, w // 5), h - max(1, h // 5), w, h),
    ]
    for box in corner_boxes:
        crop = gray.crop(box).resize((30, 30))
        samples.extend(list(crop.getdata()))
    background_mean = mean(samples) if samples else 0
    contrast = abs(receipt_mean - background_mean)
    return {
        'receipt_mean_luminance': round(receipt_mean, 2),
        'background_mean_luminance': round(background_mean, 2),
        'receipt_background_contrast_score': round(contrast, 2),
        'contrast_quality': 'low' if contrast < 25 else 'medium' if contrast < 55 else 'high',
    }


def _crop_receipt(image: Image.Image, bbox: tuple[int, int, int, int] | None) -> Image.Image:
    if bbox is None:
        return image.copy()
    left, top, right, bottom = bbox
    return image.crop((left, top, right, bottom))


def _prepare_contrast(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    autocontrast = ImageOps.autocontrast(gray, cutoff=1)
    return ImageEnhance.Contrast(autocontrast).enhance(1.8)


def _local_contrast(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    autocontrast = ImageOps.autocontrast(gray, cutoff=0.5)
    sharp = autocontrast.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=4))
    return ImageEnhance.Contrast(sharp).enhance(1.35)


def _light_sharpen(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    autocontrast = ImageOps.autocontrast(gray, cutoff=0.5)
    return autocontrast.filter(ImageFilter.UnsharpMask(radius=1.0, percent=80, threshold=6))


def _threshold_image(image: Image.Image) -> Image.Image:
    gray = _prepare_contrast(image)
    hist = gray.histogram()
    total = sum(hist) or 1
    cumulative = 0
    threshold = 170
    for index, count in enumerate(hist):
        cumulative += count
        if cumulative / total >= 0.55:
            threshold = max(120, min(210, index + 20))
            break
    return gray.point(lambda pixel: 255 if pixel > threshold else 0, mode='1').convert('L')


def _line_detection_preview(image: Image.Image) -> tuple[Image.Image, dict[str, Any]]:
    threshold = _threshold_image(image)
    data = threshold.load()
    width, height = threshold.size
    row_dark_counts: list[int] = []
    step = max(1, width // 600)
    for y in range(height):
        dark = 0
        for x in range(0, width, step):
            if data[x, y] < 128:
                dark += 1
        row_dark_counts.append(dark)
    max_count = max(row_dark_counts or [1])
    active = [count > max(4, max_count * 0.12) for count in row_dark_counts]
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for y, is_active in enumerate(active):
        if is_active and start is None:
            start = y
        elif not is_active and start is not None:
            if y - start >= 2:
                bands.append((start, y - 1))
            start = None
    if start is not None and height - start >= 2:
        bands.append((start, height - 1))

    merged: list[tuple[int, int]] = []
    for band in bands:
        if not merged or band[0] - merged[-1][1] > 5:
            merged.append(band)
        else:
            merged[-1] = (merged[-1][0], band[1])

    overlay = image.convert('RGB').copy()
    draw = ImageDraw.Draw(overlay)
    for top, bottom in merged:
        if bottom - top > max(2, height // 80):
            draw.rectangle((0, top, width - 1, bottom), outline=(0, 160, 255), width=max(1, width // 500))
    metrics = {
        'detected_line_band_count': len(merged),
        'line_band_heights': [bottom - top + 1 for top, bottom in merged[:80]],
        'line_band_y_ranges': [[top, bottom] for top, bottom in merged[:80]],
        'diagnostic_quality': 'failed_single_full_image_band' if len(merged) == 1 and merged[0][1] - merged[0][0] > height * 0.80 else 'diagnostic_only',
    }
    return overlay, metrics


def _estimate_skew_angle_from_bbox(bbox: tuple[int, int, int, int] | None, image: Image.Image) -> dict[str, Any]:
    if bbox is None:
        return {'estimated_skew_angle_degrees': None, 'method': 'not_available_no_bbox'}
    left, top, right, bottom = bbox
    bbox_width = max(1, right - left)
    bbox_height = max(1, bottom - top)
    return {
        'estimated_skew_angle_degrees': None,
        'method': 'not_computed_without_hough_transform',
        'bbox_aspect_ratio': round(bbox_width / bbox_height, 4),
        'bbox_area_ratio': round((bbox_width * bbox_height) / max(1, image.width * image.height), 4),
    }


def _fetch_targets() -> list[dict[str, Any]]:
    placeholders = ', '.join([f':id_{index}' for index, _ in enumerate(ACTIVE_TARGET_RECEIPT_TABLE_IDS)])
    params = {f'id_{index}': receipt_table_id for index, receipt_table_id in enumerate(ACTIVE_TARGET_RECEIPT_TABLE_IDS)}
    query = text(f'''
        SELECT
            rr.id AS raw_receipt_id,
            rr.original_filename,
            rr.mime_type,
            rr.storage_path,
            rt.id AS receipt_table_id,
            rt.total_amount,
            rt.line_count,
            rem.body_html,
            rem.body_text,
            rem.selected_part_type
        FROM receipt_tables rt
        JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
        LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
        WHERE rt.deleted_at IS NULL
          AND rt.id IN ({placeholders})
        ORDER BY CASE rt.id
            WHEN :id_0 THEN 0
            WHEN :id_1 THEN 1
            ELSE 99
        END
    ''')
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(query, params).mappings().all()]


def _ocr_metrics(lines: list[str], confidence: float | None, expected_total: Any) -> dict[str, Any]:
    normalized_lines = [re.sub(r'\s+', ' ', str(line or '')).strip() for line in lines or [] if str(line or '').strip()]
    amount_lines = [line for line in normalized_lines if _AMOUNT_RE.search(line)]
    expected_total_str = str(expected_total).replace('.', ',') if expected_total is not None else ''
    expected_total_dot = str(expected_total) if expected_total is not None else ''
    known_total_detected = bool(expected_total_str and any(expected_total_str in line or expected_total_dot in line for line in normalized_lines))
    article_like_lines = [line for line in normalized_lines if ARTICLE_HINT_RE.search(line) and _AMOUNT_RE.search(line)]
    return {
        'ocr_line_count': len(normalized_lines),
        'ocr_confidence': confidence,
        'amount_token_count': sum(len(_AMOUNT_RE.findall(line)) for line in normalized_lines),
        'amount_bearing_line_count': len(amount_lines),
        'article_block_candidate_line_count': len(article_like_lines),
        'known_total_detected': known_total_detected,
        'sample_lines': normalized_lines[:35],
        'amount_bearing_sample_lines': amount_lines[:20],
    }


def _ocr_variant(*, image: Image.Image, variant_name: str, original_filename: str, expected_total: Any) -> dict[str, Any]:
    lines, confidence = _ocr_image_text_with_paddle(_image_to_jpeg_bytes(image), f'{Path(original_filename).stem}_{variant_name}.jpg')
    return {
        'variant': variant_name,
        'image_dimensions': {'width': image.width, 'height': image.height},
        'image_stats': _image_stats(image),
        **_ocr_metrics(lines, confidence, expected_total),
    }


def _build_variants(original: Image.Image, cropped: Image.Image) -> dict[str, Image.Image]:
    return {
        'original': original.convert('RGB'),
        'crop_only': cropped.convert('RGB'),
        'crop_grayscale_no_threshold': ImageOps.grayscale(cropped).convert('RGB'),
        'crop_autocontrast': _prepare_contrast(cropped).convert('RGB'),
        'crop_sharpen_light': _light_sharpen(cropped).convert('RGB'),
        'crop_local_contrast': _local_contrast(cropped).convert('RGB'),
        'crop_threshold_diagnostic_only': _threshold_image(cropped).convert('RGB'),
    }


def _diagnose_target(record: dict[str, Any]) -> dict[str, Any]:
    filename = str(record.get('original_filename') or 'receipt')
    out_dir = OUTPUT_ROOT / f"{_safe_name(str(record.get('receipt_table_id') or 'unknown'))}_{_safe_name(filename)}"
    out_dir.mkdir(parents=True, exist_ok=True)

    storage_path = Path(str(record.get('storage_path') or ''))
    if not storage_path.exists():
        return {
            'original_filename': filename,
            'raw_receipt_id': record.get('raw_receipt_id'),
            'receipt_table_id': record.get('receipt_table_id'),
            'error': f'raw receipt file not found: {storage_path}',
            'read_only': True,
        }

    file_bytes = storage_path.read_bytes()
    parse_bytes, parse_filename, parse_mime_type = _resolve_reparse_source_payload(record, file_bytes)
    image = Image.open(io.BytesIO(parse_bytes)).convert('RGB')
    bbox = _estimate_receipt_bbox(image)
    cropped = _crop_receipt(image, bbox)
    line_overlay, line_metrics = _line_detection_preview(cropped)
    variants = _build_variants(image, cropped)

    variant_paths: dict[str, str] = {}
    for variant_name, variant_image in variants.items():
        variant_paths[variant_name] = _save_preview(variant_image, out_dir / f'variant_{variant_name}.jpg')

    ocr_comparison = [
        _ocr_variant(
            image=variant_image,
            variant_name=variant_name,
            original_filename=filename,
            expected_total=record.get('total_amount'),
        )
        for variant_name, variant_image in variants.items()
    ]

    paths = {
        'original_preview_path': _save_preview(image, out_dir / '01_original_preview.jpg'),
        'bbox_overlay_path': _save_preview(_bbox_overlay(image, bbox), out_dir / '02_receipt_bbox_overlay.jpg'),
        'cropped_receipt_preview_path': _save_preview(cropped, out_dir / '03_cropped_receipt.jpg'),
        'line_detection_preview_path': _save_preview(line_overlay, out_dir / '04_line_detection_overlay.jpg'),
        'variant_preview_paths': variant_paths,
    }

    report = {
        'original_filename': filename,
        'parse_filename': parse_filename,
        'parse_mime_type': parse_mime_type,
        'raw_receipt_id': record.get('raw_receipt_id'),
        'receipt_table_id': record.get('receipt_table_id'),
        'stored_total_amount': record.get('total_amount'),
        'stored_line_count': record.get('line_count'),
        'original_image_dimensions': {'width': image.width, 'height': image.height},
        'original_image_stats': _image_stats(image),
        'detected_receipt_bounding_box': list(bbox) if bbox is not None else None,
        'cropped_image_dimensions': {'width': cropped.width, 'height': cropped.height},
        'cropped_image_stats': _image_stats(cropped),
        'contrast_metrics': _contrast_score(image, bbox),
        'skew_diagnostics': _estimate_skew_angle_from_bbox(bbox, image),
        'line_detection_metrics': line_metrics,
        'ocr_before_after_comparison': ocr_comparison,
        'preview_paths': paths,
        'diagnostic_limitations': [
            'read-only diagnostic only; runtime parser/OCR is unchanged',
            'only the two active PLUS receipt_table_id targets are analysed',
            'bbox detection uses generic brightness segmentation and can be wrong on low-contrast or multi-receipt images',
            'threshold variant is diagnostic-only and not recommended for runtime without separate acceptance evidence',
            'skew angle is intentionally not estimated without a reliable Hough/perspective transform',
            'OCR comparison is observational and writes no OCR result to the database',
        ],
        'read_only': True,
        'database_write_intent': False,
    }
    (out_dir / 'diagnostics.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    report['preview_paths']['diagnostics_json_path'] = str(out_dir / 'diagnostics.json')
    return report


def build_report() -> dict[str, Any]:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    targets = _fetch_targets()
    reports = [_diagnose_target(record) for record in targets]
    index_path = OUTPUT_ROOT / 'index.json'
    result = {
        'test': 'R9-38B1a pre-OCR preprocessing diagnostics with OCR variant comparison',
        'active_target_receipt_table_ids': ACTIVE_TARGET_RECEIPT_TABLE_IDS,
        'output_root': str(OUTPUT_ROOT),
        'target_count': len(targets),
        'reports': reports,
        'read_only': True,
        'database_write_intent': False,
    }
    index_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    result['index_json_path'] = str(index_path)
    return result


def main() -> int:
    print(json.dumps(build_report(), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
