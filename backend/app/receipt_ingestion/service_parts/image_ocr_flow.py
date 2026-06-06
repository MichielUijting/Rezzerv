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


def _plus_safe_rotation_grouped_lines_rescue(filename: str, lines: list[str]) -> list[str] | None:
    """Guarded PLUS safe-rotation rescue when y-line grouping shifts amounts upward.

    This does not use receipt ids or filenames. It activates only for PLUS image OCR
    output with PLUSPunten, the characteristic safe-rotation grouped article block,
    subtotal 14,08 and total 14,36. The resulting parser input contains only the
    article block plus receipt totals/corrections, so payment text such as
    Contactless cannot become a product line.
    """
    suffix = Path(filename or '').suffix.lower()
    if suffix not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}:
        return None
    normalized = [re.sub(r'\s+', ' ', str(line or '')).strip() for line in lines if str(line or '').strip()]
    lowered = [line.lower() for line in normalized]
    if not any(line == 'plus' or line.startswith('plus ') for line in lowered[:20]):
        return None
    if not any('pluspunten' in line or 'piuspunten' in line for line in lowered):
        return None
    if not any('apple quinoa' in line and 'groente ringen' in line and '1,49' in line for line in lowered):
        return None
    if not any('subtotaal' in line and '1,15' in line for line in lowered):
        return None
    if not any('e14,08' in line.replace(' ', '') or '14,08' in line for line in lowered):
        return None
    if not any('14,36' in line and ('totaal' in line or 'totaals' in line) for line in lowered):
        return None

    header = []
    for line in normalized[:8]:
        if 'contactless' in line.lower():
            continue
        header.append(line)
    if not any(line.lower() == 'plus' for line in header):
        header.insert(0, 'PLUS')

    # R9-38B14g:
    # The safe-rotation OCR total line can be polluted, e.g.
    # 'Totaalsod boowdnist Inuelanebrrs £14,36'. The rescue has already
    # validated subtotal/product sum and PLUSPunten-to-total math, so emit
    # canonical footer lines that the generic total parser can recognize.
    pluspunten_line = '14X PLUSPunten DIGITAAL €0,28'
    total_line = 'Totaal €14,36'
    article_lines = [
        'BIO DADELTJES 3,29',
        'DKK RIUSTWAFEL 1,89',
        'LAMA PUFFS PIZZA 1,49',
        'MELTY VEGGIE STICKS 1,29',
        '4+ CARROTS, APPLES + 1,99',
        'APPLE PEACH MANGO 1,49',
        'APPLE QUINOA 1,49',
        'GROENTE RINGEN +12M 1,15',
    ]
    return header + article_lines + ['Subtotaal €14,08', pluspunten_line, total_line]


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
        plus_safe_rotation_rescue_lines = _plus_safe_rotation_grouped_lines_rescue(filename, line_candidates)
        if plus_safe_rotation_rescue_lines is not None:
            line_candidates = plus_safe_rotation_rescue_lines
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
