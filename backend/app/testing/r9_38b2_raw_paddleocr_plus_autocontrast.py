from __future__ import annotations

import io
import json
import re
import tempfile
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from sqlalchemy import text

from app.db import engine
from app.receipt_ingestion.service_parts.image_ocr_flow import (
    _extract_payload_from_paddle_item,
    _get_paddle_ocr,
    _group_paddle_texts_to_lines,
    _normalize_paddle_collection,
)
from app.services.receipt_service import _resolve_reparse_source_payload

TARGET_RECEIPT_TABLE_ID = '7323172c2f364be5b53be9e11efb1ef4'
SOURCE_VARIANT = 'variant_crop_autocontrast'
OUTPUT_ROOT = Path('/tmp/rezzerv_raw_ocr_diagnostics/r9_38b2')


def _safe_name(value: str) -> str:
    return re.sub(r'[^a-zA-Z0-9._-]+', '_', str(value or 'receipt')).strip('_') or 'receipt'


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, 'tolist'):
        try:
            return _jsonable(value.tolist())
        except Exception:
            pass
    return str(value)


def _fetch_target() -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(text('''
            SELECT rr.id AS raw_receipt_id, rr.original_filename, rr.mime_type,
                   rr.storage_path, rt.id AS receipt_table_id, rt.total_amount,
                   rt.line_count, rem.body_html, rem.body_text, rem.selected_part_type
            FROM receipt_tables rt
            JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
            LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
            WHERE rt.deleted_at IS NULL AND rt.id = :receipt_table_id
            LIMIT 1
        '''), {'receipt_table_id': TARGET_RECEIPT_TABLE_ID}).mappings().first()
    if row is None:
        raise RuntimeError(f'Active receipt_table_id not found: {TARGET_RECEIPT_TABLE_ID}')
    return dict(row)


def _estimate_receipt_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    gray = ImageOps.grayscale(image)
    scale = min(1.0, 900 / max(gray.size))
    small = gray.resize((int(gray.width * scale), int(gray.height * scale)), Image.LANCZOS) if scale < 1 else gray
    blurred = small.filter(ImageFilter.GaussianBlur(radius=2))
    pixels = blurred.load()
    width, height = blurred.size
    hist = blurred.histogram()
    total = sum(hist) or 1
    cumulative = 0
    p70 = 180
    for i, count in enumerate(hist):
        cumulative += count
        if cumulative / total >= 0.70:
            p70 = i
            break
    threshold = max(120, min(235, p70 + 8))
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
    left, right, top, bottom = pct(xs, 0.02), pct(xs, 0.98), pct(ys, 0.02), pct(ys, 0.98)
    mx, my = max(4, int((right - left) * 0.025)), max(4, int((bottom - top) * 0.025))
    inv = 1.0 / scale
    return int(max(0, left - mx) * inv), int(max(0, top - my) * inv), int(min(width - 1, right + mx) * inv), int(min(height - 1, bottom + my) * inv)


def _autocontrast_variant(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    return ImageEnhance.Contrast(ImageOps.autocontrast(gray, cutoff=1)).enhance(1.8).convert('RGB')


def _bbox_anchor(bbox: Any) -> dict[str, Any]:
    try:
        points: list[tuple[float, float]] = []
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and not isinstance(bbox[0], (list, tuple)):
            x1, y1, x2, y2 = [float(v) for v in bbox]
            points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        else:
            for point in bbox or []:
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    points.append((float(point[0]), float(point[1])))
        if not points:
            return {'center_y': None, 'height': None, 'min_x': None, 'max_x': None}
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return {'center_y': round((min(ys) + max(ys)) / 2, 3), 'height': round(max(ys) - min(ys), 3), 'min_x': round(min(xs), 3), 'max_x': round(max(xs), 3), 'min_y': round(min(ys), 3), 'max_y': round(max(ys), 3)}
    except Exception as exc:
        return {'center_y': None, 'height': None, 'min_x': None, 'max_x': None, 'error': str(exc)}


def _extract_raw_payload(result: Any) -> dict[str, Any]:
    payloads: list[dict[str, Any]] = []
    fragments: list[dict[str, Any]] = []
    all_texts: list[str] = []
    all_boxes: list[Any] = []
    all_scores: list[float] = []
    for item_index, item in enumerate(_normalize_paddle_collection(result)):
        payload = _extract_payload_from_paddle_item(item)
        payloads.append(_jsonable(payload))
        texts = [str(t) for t in _normalize_paddle_collection(payload.get('rec_texts') or payload.get('texts')) if str(t).strip()]
        scores_raw = _normalize_paddle_collection(payload.get('rec_scores') or payload.get('scores'))
        boxes = payload.get('rec_boxes'); box_source = 'rec_boxes'
        if boxes is None:
            boxes = payload.get('dt_polys'); box_source = 'dt_polys'
        if boxes is None:
            boxes = payload.get('rec_polys'); box_source = 'rec_polys'
        boxes_list = _normalize_paddle_collection(boxes)
        for local_index, text_value in enumerate(texts):
            bbox = boxes_list[local_index] if local_index < len(boxes_list) else None
            score = None
            if local_index < len(scores_raw):
                try: score = float(scores_raw[local_index])
                except Exception: score = None
            if score is not None:
                all_scores.append(score)
            all_texts.append(text_value)
            if bbox is not None:
                all_boxes.append(bbox)
            fragments.append({'global_index': len(fragments), 'item_index': item_index, 'local_index': local_index, 'text': text_value, 'score': score, 'bbox_source': box_source if bbox is not None else None, 'bbox': _jsonable(bbox), **_bbox_anchor(bbox)})
    heights = [float(a['height']) for a in (_bbox_anchor(b) for b in all_boxes) if isinstance(a.get('height'), (int, float)) and a['height'] > 0]
    return {
        'raw_result_payloads': payloads,
        'raw_fragment_table': fragments,
        'current_grouped_lines_for_comparison_only': _group_paddle_texts_to_lines(all_texts, all_boxes if all_boxes else None),
        'current_grouping_parameters_for_comparison_only': {
            'fragment_count': len(fragments),
            'median_box_height': round(median(heights), 3) if heights else None,
            'merge_threshold': round(max(12.0, (median(heights) if heights else 12.0) * 0.7), 3),
            'confidence_average': round(sum(all_scores) / len(all_scores), 4) if all_scores else None,
        },
    }


def build_report() -> dict[str, Any]:
    record = _fetch_target()
    filename = str(record.get('original_filename') or 'receipt')
    out_dir = OUTPUT_ROOT / f'{TARGET_RECEIPT_TABLE_ID}_{_safe_name(filename)}'
    out_dir.mkdir(parents=True, exist_ok=True)
    file_bytes = Path(str(record.get('storage_path'))).read_bytes()
    parse_bytes, parse_filename, parse_mime_type = _resolve_reparse_source_payload(record, file_bytes)
    original = Image.open(io.BytesIO(parse_bytes)).convert('RGB')
    bbox = _estimate_receipt_bbox(original)
    cropped = original.crop(bbox) if bbox else original
    variant = _autocontrast_variant(cropped)
    variant_path = out_dir / f'{SOURCE_VARIANT}.jpg'
    variant.save(variant_path, format='JPEG', quality=95)
    model = _get_paddle_ocr()
    if model is None:
        raise RuntimeError('PaddleOCR model is not available')
    with tempfile.TemporaryDirectory(prefix='rezzerv-r9-38b2-') as temp_dir:
        image_path = Path(temp_dir) / f'{Path(filename).stem}_{SOURCE_VARIANT}.jpg'
        variant.save(image_path, format='JPEG', quality=95)
        raw_result = model.predict(str(image_path))
    result = {
        'test': 'R9-38B2 raw PaddleOCR output export',
        'read_only': True,
        'database_write_intent': False,
        'parser_invoked': False,
        'line_grouping_applied_to_raw_output': False,
        'normalization_applied_to_raw_output': False,
        'target': {'receipt_table_id': TARGET_RECEIPT_TABLE_ID, 'raw_receipt_id': record.get('raw_receipt_id'), 'original_filename': filename, 'parse_filename': parse_filename, 'parse_mime_type': parse_mime_type, 'stored_total_amount': record.get('total_amount'), 'stored_line_count': record.get('line_count')},
        'source_variant': SOURCE_VARIANT,
        'variant_image_path': str(variant_path),
        'detected_receipt_bounding_box': list(bbox) if bbox else None,
        'variant_image_dimensions': {'width': variant.width, 'height': variant.height},
        **_extract_raw_payload(raw_result),
    }
    output_path = out_dir / 'raw_paddleocr_output.json'
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    result['output_json_path'] = str(output_path)
    (OUTPUT_ROOT / 'index.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    result['index_json_path'] = str(OUTPUT_ROOT / 'index.json')
    return result


def main() -> int:
    print(json.dumps(build_report(), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
