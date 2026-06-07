"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

import io
import logging
import re
import tempfile
from pathlib import Path
from statistics import median
from typing import Any

from app.receipt_ingestion.service_parts.plus_photo_line_grouping_fallback import (
    apply_plus_photo_line_grouping_fallback,
    diagnose_plus_photo_line_grouping_fallback,
)

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except Exception:  # pragma: no cover
    Image = None
    ImageEnhance = None
    ImageFilter = None
    ImageOps = None

LOGGER = logging.getLogger(__name__)
_MAX_SIDE = 1600


def _normalize_collection(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, 'tolist'):
        try:
            value = value.tolist()
        except Exception:
            pass
    if isinstance(value, (str, bytes, bytearray)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _extract_payload(item: Any) -> dict[str, Any]:
    candidates = [item]
    for attr_name in ('res', 'json', 'result'):
        attr = getattr(item, attr_name, None)
        if attr is None:
            continue
        try:
            candidates.append(attr() if callable(attr) else attr)
        except TypeError:
            candidates.append(attr)
    to_dict = getattr(item, 'to_dict', None)
    if callable(to_dict):
        try:
            candidates.append(to_dict())
        except Exception:
            pass
    for candidate in candidates:
        if isinstance(candidate, dict):
            if isinstance(candidate.get('res'), dict):
                return candidate['res']
            return candidate
    return {}


def _extract_texts_scores_boxes(result: Any) -> tuple[list[str], list[float], list[Any]]:
    texts: list[str] = []
    scores: list[float] = []
    boxes: list[Any] = []
    for item in _normalize_collection(result):
        payload = _extract_payload(item)
        current_texts = _normalize_collection(payload.get('rec_texts') or payload.get('texts'))
        current_scores = _normalize_collection(payload.get('rec_scores') or payload.get('scores'))
        current_boxes = payload.get('rec_boxes')
        if current_boxes is None:
            current_boxes = payload.get('dt_polys')
        if current_boxes is None:
            current_boxes = payload.get('rec_polys')
        current_boxes = _normalize_collection(current_boxes)
        normalized_texts = [str(text) for text in current_texts if str(text).strip()]
        texts.extend(normalized_texts)
        for score in current_scores:
            try:
                scores.append(float(score))
            except (TypeError, ValueError):
                continue
        boxes.extend(current_boxes[: len(normalized_texts)])
    return texts, scores, boxes


def _bbox_anchor(box: Any) -> tuple[float, float, float] | None:
    try:
        if isinstance(box, (list, tuple)) and len(box) == 4 and not isinstance(box[0], (list, tuple)):
            x1, y1, x2, y2 = [float(v) for v in box]
            return ((y1 + y2) / 2.0, min(x1, x2), max(1.0, abs(y2 - y1)))
        points = []
        for point in box or []:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append((float(point[0]), float(point[1])))
        if not points:
            return None
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return ((min(ys) + max(ys)) / 2.0, min(xs), max(1.0, max(ys) - min(ys)))
    except Exception:
        return None


def _group_to_lines(texts: list[str], boxes: list[Any]) -> list[str]:
    if not texts:
        return []
    if not boxes or len(texts) != len(boxes):
        return [re.sub(r'\s+', ' ', str(text)).strip() for text in texts if str(text).strip()]
    fragments = []
    heights = []
    for text, box in zip(texts, boxes):
        normalized = re.sub(r'\s+', ' ', str(text or '')).strip()
        if not normalized:
            continue
        anchor = _bbox_anchor(box)
        if anchor is None:
            continue
        center_y, min_x, height = anchor
        heights.append(height)
        fragments.append((center_y, min_x, normalized))
    fragments.sort(key=lambda item: (item[0], item[1]))
    threshold = max(12.0, (median(heights) if heights else 12.0) * 0.7)
    grouped: list[list[tuple[float, float, str]]] = []
    for fragment in fragments:
        if not grouped:
            grouped.append([fragment])
            continue
        current_y = sum(item[0] for item in grouped[-1]) / len(grouped[-1])
        if abs(fragment[0] - current_y) <= threshold:
            grouped[-1].append(fragment)
        else:
            grouped.append([fragment])
    lines = []
    for group in grouped:
        group.sort(key=lambda item: item[1])
        line = re.sub(r'\s+', ' ', ' '.join(item[2] for item in group)).strip()
        if line:
            lines.append(line)
    return lines


def _estimate_bbox(image: Any) -> tuple[int, int, int, int] | None:
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
    for index, count in enumerate(hist):
        cumulative += count
        if cumulative / total >= 0.70:
            p70 = index
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


def _preprocess_bytes(file_bytes: bytes) -> bytes | None:
    if Image is None or ImageOps is None or ImageEnhance is None or ImageFilter is None:
        return None
    try:
        original = Image.open(io.BytesIO(file_bytes)).convert('RGB')
        bbox = _estimate_bbox(original)
        cropped = original.crop(bbox) if bbox else original
        gray = ImageOps.grayscale(cropped)
        variant = ImageEnhance.Contrast(ImageOps.autocontrast(gray, cutoff=1)).enhance(1.8).convert('RGB')
        width, height = variant.size
        scale = min(1.0, _MAX_SIDE / max(width, height))
        if scale < 1.0:
            variant = variant.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.LANCZOS)
        buffer = io.BytesIO()
        variant.save(buffer, format='JPEG', quality=92)
        return buffer.getvalue()
    except Exception as exc:
        LOGGER.warning('PLUS preprocessed fallback image preparation failed: %s', exc)
        return None


def guarded_plus_preprocessed_ocr_fallback(
    *,
    model: Any,
    file_bytes: bytes,
    filename: str,
    runtime_texts: list[str],
    runtime_boxes: list[Any],
    runtime_lines: list[str],
) -> dict[str, Any]:
    runtime_diagnostics = diagnose_plus_photo_line_grouping_fallback(
        filename=filename,
        texts=runtime_texts,
        boxes=runtime_boxes,
        current_lines=runtime_lines,
    )
    result: dict[str, Any] = {
        'runtime_diagnostics': runtime_diagnostics,
        'preprocessed_attempted': False,
        'preprocessed_diagnostics': None,
        'preprocessed_lines': None,
        'preprocessed_scores': [],
        'fallback_lines': None,
    }
    allow_preprocessed = (
        runtime_diagnostics.get('is_image_receipt')
        and runtime_diagnostics.get('texts_boxes_same_length')
        and runtime_diagnostics.get('looks_like_plus_receipt')
        and runtime_diagnostics.get('has_suspicious_article_merges')
    )
    if not allow_preprocessed:
        return result
    preprocessed = _preprocess_bytes(file_bytes)
    if not preprocessed:
        return result
    result['preprocessed_attempted'] = True
    try:
        with tempfile.TemporaryDirectory(prefix='rezzerv-plus-preprocessed-') as temp_dir:
            image_path = Path(temp_dir) / 'plus_fallback_preprocessed.jpg'
            image_path.write_bytes(preprocessed)
            raw_result = model.predict(str(image_path))
    except Exception as exc:
        LOGGER.warning('PLUS preprocessed fallback OCR failed for %s: %s', filename, exc)
        return result
    pre_texts, pre_scores, pre_boxes = _extract_texts_scores_boxes(raw_result)
    pre_lines = _group_to_lines(pre_texts, pre_boxes)
    pre_diag = diagnose_plus_photo_line_grouping_fallback(
        filename='plus_fallback_preprocessed.jpg',
        texts=pre_texts,
        boxes=pre_boxes,
        current_lines=pre_lines,
    )
    result['preprocessed_diagnostics'] = pre_diag
    result['preprocessed_lines'] = pre_lines
    result['preprocessed_scores'] = pre_scores
    if pre_diag.get('fallback_applied'):
        result['fallback_lines'] = list(pre_diag.get('final_lines_after_fallback') or [])
    return result
