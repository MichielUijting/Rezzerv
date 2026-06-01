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
from app.services.receipt_service import _resolve_reparse_source_payload

TARGET_PATTERNS = (
    'plus foto 1',
    'plus foto 2',
)
OUTPUT_ROOT = Path('/tmp/rezzerv_preprocessing_diagnostics/r9_38b1')
MAX_PREVIEW_SIDE = 1800


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


def _estimate_receipt_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Estimate receipt rectangle using only generic brightness/background contrast.

    This intentionally avoids store/file-specific assumptions and does not alter
    runtime OCR. It is diagnostic-only and conservative.
    """
    gray = ImageOps.grayscale(image)
    small_max = 900
    scale = min(1.0, small_max / max(gray.size))
    small = gray.resize((int(gray.width * scale), int(gray.height * scale)), Image.LANCZOS) if scale < 1.0 else gray
    blurred = small.filter(ImageFilter.GaussianBlur(radius=2))
    pixels = blurred.load()
    width, height = blurred.size

    # Estimate dark background / light paper separation by using relative local brightness.
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

    # Background sample from corners outside the bbox.
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
    enhanced = ImageEnhance.Contrast(autocontrast).enhance(1.8)
    return enhanced


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
    gray = _prepare_contrast(image)
    threshold = _threshold_image(image)
    data = threshold.load()
    width, height = threshold.size
    row_dark_counts: list[int] = []
    for y in range(height):
        dark = 0
        for x in range(0, width, max(1, width // 600)):
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

    # Merge very close bands caused by letter ascenders/descenders.
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
    }
    return overlay, metrics


def _estimate_skew_angle_from_bbox(bbox: tuple[int, int, int, int] | None, image: Image.Image) -> dict[str, Any]:
    # Without OpenCV/Hough transforms this diagnostic intentionally reports only
    # coarse geometry. It avoids pretending to have a reliable deskew angle.
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
    where = ' OR '.join(['LOWER(rr.original_filename) LIKE :pattern_' + str(index) for index, _ in enumerate(TARGET_PATTERNS)])
    params = {f'pattern_{index}': f'%{pattern}%' for index, pattern in enumerate(TARGET_PATTERNS)}
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
        FROM raw_receipts rr
        LEFT JOIN receipt_tables rt ON rt.raw_receipt_id = rr.id AND rt.deleted_at IS NULL
        LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
        WHERE {where}
        ORDER BY rr.original_filename, rt.id
    ''')
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(query, params).mappings().all()]


def _diagnose_target(record: dict[str, Any]) -> dict[str, Any]:
    filename = str(record.get('original_filename') or 'receipt')
    out_dir = OUTPUT_ROOT / _safe_name(filename)
    out_dir.mkdir(parents=True, exist_ok=True)

    storage_path = Path(str(record.get('storage_path') or ''))
    if not storage_path.exists():
        return {
            'original_filename': filename,
            'raw_receipt_id': record.get('raw_receipt_id'),
            'error': f'raw receipt file not found: {storage_path}',
            'read_only': True,
        }

    file_bytes = storage_path.read_bytes()
    parse_bytes, parse_filename, parse_mime_type = _resolve_reparse_source_payload(record, file_bytes)
    image = Image.open(io.BytesIO(parse_bytes)).convert('RGB')
    bbox = _estimate_receipt_bbox(image)
    cropped = _crop_receipt(image, bbox)
    contrast = _prepare_contrast(cropped)
    threshold = _threshold_image(cropped)
    line_overlay, line_metrics = _line_detection_preview(cropped)

    paths = {
        'original_preview_path': _save_preview(image, out_dir / '01_original_preview.jpg'),
        'bbox_overlay_path': _save_preview(_bbox_overlay(image, bbox), out_dir / '02_receipt_bbox_overlay.jpg'),
        'cropped_receipt_preview_path': _save_preview(cropped, out_dir / '03_cropped_receipt.jpg'),
        'contrast_preview_path': _save_preview(contrast.convert('RGB'), out_dir / '04_contrast_receipt.jpg'),
        'threshold_preview_path': _save_preview(threshold.convert('RGB'), out_dir / '05_threshold_receipt.jpg'),
        'line_detection_preview_path': _save_preview(line_overlay, out_dir / '06_line_detection_overlay.jpg'),
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
        'preview_paths': paths,
        'diagnostic_limitations': [
            'read-only diagnostic only; runtime parser/OCR is unchanged',
            'bbox detection uses generic brightness segmentation and can be wrong on low-contrast images',
            'skew angle is intentionally not estimated without a reliable Hough/perspective transform',
            'line bands are image-preprocessing hints, not OCR truth',
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
        'test': 'R9-38B1 pre-OCR receipt photo preprocessing diagnostics',
        'target_patterns': TARGET_PATTERNS,
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
