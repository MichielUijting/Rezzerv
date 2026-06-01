from __future__ import annotations

import io
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from statistics import median
from typing import Any

from app.receipt_ingestion.service_parts.plus_photo_line_grouping_fallback import apply_plus_photo_line_grouping_fallback
from app.receipt_ingestion.service_parts.plus_photo_preprocessed_fallback_ocr import guarded_plus_preprocessed_ocr_fallback
from app.receipt_ingestion.service_parts.text_extraction import _normalize_text_lines

try:
    from paddleocr import PaddleOCR
except Exception:  # pragma: no cover
    PaddleOCR = None

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

LOGGER = logging.getLogger(__name__)
_PADDLE_OCR_INSTANCE = None


def _get_paddle_ocr():
    global _PADDLE_OCR_INSTANCE
    if _PADDLE_OCR_INSTANCE is not None:
        return _PADDLE_OCR_INSTANCE
    if PaddleOCR is None:
        return None

    constructors = [
        {
            'use_doc_orientation_classify': False,
            'use_doc_unwarping': False,
            'use_textline_orientation': False,
            'lang': 'en',
        },
        {
            'use_angle_cls': True,
            'lang': 'en',
        },
        {
            'lang': 'en',
        },
    ]
    for kwargs in constructors:
        try:
            _PADDLE_OCR_INSTANCE = PaddleOCR(**kwargs)
            break
        except TypeError:
            continue
        except Exception as exc:  # pragma: no cover - runtime dependency/model download issue
            LOGGER.warning('PaddleOCR initialisatie mislukt: %s', exc)
            return None
    return _PADDLE_OCR_INSTANCE


def _ocr_bbox_to_line_anchor(bbox: Any) -> tuple[float, float, float] | None:
    if bbox is None:
        return None
    try:
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and not isinstance(bbox[0], (list, tuple)):
            x1, y1, x2, y2 = [float(v) for v in bbox]
            return ((y1 + y2) / 2.0, x1, max(1.0, y2 - y1))
        points = []
        for point in bbox:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            points.append((float(point[0]), float(point[1])))
        if not points:
            return None
        xs = [pt[0] for pt in points]
        ys = [pt[1] for pt in points]
        return ((min(ys) + max(ys)) / 2.0, min(xs), max(1.0, max(ys) - min(ys)))
    except Exception:
        return None


def _extract_payload_from_paddle_item(item: Any) -> dict[str, Any]:
    candidates: list[Any] = [item]
    for attr_name in ('res', 'json', 'result'):
        attr = getattr(item, attr_name, None)
        if attr is None:
            continue
        try:
            value = attr() if callable(attr) else attr
        except TypeError:
            value = attr
        candidates.append(value)
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


def _group_paddle_texts_to_lines(texts: list[str], boxes: list[Any] | None) -> list[str]:
    if not texts:
        return []
    if not boxes or len(boxes) != len(texts):
        return [re.sub(r'\s+', ' ', text).strip() for text in texts if str(text).strip()]

    fragments: list[tuple[float, float, float, str]] = []
    heights: list[float] = []
    for text_value, box in zip(texts, boxes):
        normalized_text = re.sub(r'\s+', ' ', str(text_value or '')).strip()
        if not normalized_text:
            continue
        anchor = _ocr_bbox_to_line_anchor(box)
        if anchor is None:
            fragments.append((float(len(fragments) * 100), float(len(fragments)), 10.0, normalized_text))
            continue
        center_y, min_x, height = anchor
        heights.append(height)
        fragments.append((center_y, min_x, height, normalized_text))

    if not fragments:
        return []

    fragments.sort(key=lambda item: (item[0], item[1]))
    merge_threshold = max(12.0, (median(heights) if heights else 12.0) * 0.7)
    grouped: list[list[tuple[float, float, float, str]]] = []
    for fragment in fragments:
        if not grouped:
            grouped.append([fragment])
            continue
        current_group = grouped[-1]
        current_y = sum(part[0] for part in current_group) / len(current_group)
        if abs(fragment[0] - current_y) <= merge_threshold:
            current_group.append(fragment)
        else:
            grouped.append([fragment])

    result_lines: list[str] = []
    for group in grouped:
        group.sort(key=lambda item: item[1])
        merged = ' '.join(part[3] for part in group).strip()
        merged = re.sub(r'\s+', ' ', merged)
        if merged:
            result_lines.append(merged)
    return result_lines


def _normalize_paddle_collection(value: Any) -> list[Any]:
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


def _ocr_image_text_with_paddle(file_bytes: bytes, filename: str) -> tuple[list[str], float | None]:
    model = _get_paddle_ocr()
    if model is None:
        return [], None

    suffix = Path(filename).suffix.lower() or '.png'
    try:
        with tempfile.TemporaryDirectory(prefix='rezzerv-paddleocr-') as temp_dir:
            image_path = Path(temp_dir) / f'image{suffix}'
            image_path.write_bytes(file_bytes)
            result = model.predict(str(image_path))
    except Exception as exc:  # pragma: no cover - runtime dependency/model download issue
        LOGGER.warning('PaddleOCR verwerking mislukt voor %s: %s', filename, exc)
        return [], None

    texts: list[str] = []
    scores: list[float] = []
    boxes: list[Any] = []
    for item in _normalize_paddle_collection(result):
        payload = _extract_payload_from_paddle_item(item)
        current_texts = _normalize_paddle_collection(payload.get('rec_texts') or payload.get('texts'))
        current_scores = _normalize_paddle_collection(payload.get('rec_scores') or payload.get('scores'))
        current_boxes = payload.get('rec_boxes')
        if current_boxes is None:
            current_boxes = payload.get('dt_polys')
        if current_boxes is None:
            current_boxes = payload.get('rec_polys')
        current_boxes = _normalize_paddle_collection(current_boxes)
        normalized_texts = [str(text) for text in current_texts if str(text).strip()]
        texts.extend(normalized_texts)
        for score in current_scores:
            try:
                scores.append(float(score))
            except (TypeError, ValueError):
                continue
        boxes.extend(current_boxes[: len(normalized_texts)])

    line_candidates = _group_paddle_texts_to_lines(texts, boxes if boxes else None)
    plus_fallback_lines = apply_plus_photo_line_grouping_fallback(
        filename=filename,
        texts=texts,
        boxes=boxes,
        current_lines=line_candidates,
    )
    if plus_fallback_lines is not None:
        line_candidates = plus_fallback_lines
    else:
        preprocessed_result = guarded_plus_preprocessed_ocr_fallback(
            model=model,
            file_bytes=file_bytes,
            filename=filename,
            runtime_texts=texts,
            runtime_boxes=boxes,
            runtime_lines=line_candidates,
        )
        if preprocessed_result.get('fallback_lines'):
            line_candidates = list(preprocessed_result['fallback_lines'])
            pre_scores = preprocessed_result.get('preprocessed_scores') or []
            if pre_scores:
                scores = [float(score) for score in pre_scores]
    confidence = round(sum(scores) / len(scores), 4) if scores else None
    return line_candidates, confidence


def warm_receipt_ocr_runtime() -> dict[str, Any]:
    """Warm OCR dependencies before the first user upload."""
    result: dict[str, Any] = {"warmup": "receipt_ocr_runtime"}
    if str(os.getenv("REZZERV_RECEIPT_STARTUP_OCR_WARMUP", "false") or "false").strip().lower() not in {"1", "true", "yes", "on"}:
        result["paddle"] = "skipped"
        result["reason"] = "startup_ocr_warmup_disabled"
        return result
    try:
        if Image is None:
            result["paddle"] = "pillow_unavailable"
            return result
        sample = Image.new("RGB", (320, 220), "white")
        buffer = io.BytesIO()
        sample.save(buffer, format="PNG")
        paddle_lines, _ = _ocr_image_text_with_paddle(buffer.getvalue(), "warmup.png")
        result["paddle"] = "ok" if paddle_lines is not None else "no_lines"
    except Exception as exc:
        result["paddle"] = f"failed:{type(exc).__name__}"
    return result


def _ocr_image_text_with_tesseract(file_bytes: bytes, filename: str) -> tuple[list[str], float | None]:
    suffix = Path(filename).suffix.lower() or '.png'
    language = 'nld+eng'
    try:
        with tempfile.TemporaryDirectory(prefix='rezzerv-tesseract-') as temp_dir:
            image_path = Path(temp_dir) / f'image{suffix}'
            image_path.write_bytes(file_bytes)
            command = ['tesseract', str(image_path), 'stdout', '-l', language, '--psm', '6']
            completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
            if completed.returncode != 0:
                LOGGER.warning('Tesseract verwerking mislukt voor %s: %s', filename, (completed.stderr or '').strip())
                return [], None
            text_output = completed.stdout or ''
            return _normalize_text_lines(text_output), None
    except Exception as exc:  # pragma: no cover - runtime dependency
        LOGGER.warning('Tesseract fallback mislukt voor %s: %s', exc)
        return [], None
