"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
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
from pathlib import Path

from PIL import Image, ImageOps

LOGGER = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover
    cv2 = None
    np = None

DEBUG_DIR = Path('/app/data/receipts/debug')
DEBUG_OUTPUT_PATH = DEBUG_DIR / 'latest-ocr-preprocessed.png'
DEBUG_ORIGINAL_PATH = DEBUG_DIR / 'latest-ocr-00-original.png'
DEBUG_ROTATED_PATH = DEBUG_DIR / 'latest-ocr-01-rotated.png'
DEBUG_FINAL_PATH = DEBUG_DIR / 'latest-ocr-02-final.png'
MAX_OCR_SIDE = 2600


def _shape_text(rgb) -> str:
    if rgb is None:
        return 'None'
    height, width = rgb.shape[:2]
    channels = rgb.shape[2] if len(rgb.shape) > 2 else 1
    return f'{width}x{height}x{channels}'


def _encode_png(rgb) -> bytes:
    image = Image.fromarray(rgb)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def _write_debug_png(path: Path, rgb, reason: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_encode_png(rgb))
        LOGGER.warning('Receipt preprocessing DEBUG_WRITE path=%s reason=%s shape=%s', path, reason, _shape_text(rgb))
    except Exception as exc:
        LOGGER.warning('Receipt preprocessing DEBUG_WRITE_FAILED path=%s reason=%s error=%s', path, reason, exc)


def _resize_max_side(rgb, max_side: int = MAX_OCR_SIDE):
    height, width = rgb.shape[:2]
    largest = max(height, width)
    if largest <= max_side:
        return rgb
    scale = max_side / float(largest)
    return cv2.resize(rgb, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)


def _rotate_keep_bounds(rgb, angle: float):
    height, width = rgb.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_width = int((height * sin) + (width * cos))
    new_height = int((height * cos) + (width * sin))
    matrix[0, 2] += (new_width / 2.0) - center[0]
    matrix[1, 2] += (new_height / 2.0) - center[1]
    return cv2.warpAffine(rgb, matrix, (new_width, new_height), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))


def _normalize_line_angle(angle: float) -> float:
    while angle <= -90:
        angle += 180
    while angle > 90:
        angle -= 180
    if angle > 45:
        angle -= 90
    elif angle < -45:
        angle += 90
    return float(angle)


def _dominant_receipt_contour_rotation_angle(rgb) -> float | None:
    height, width = rgb.shape[:2]
    image_area = float(height * width)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 0)
    edges = cv2.Canny(blurred, 50, 150)
    kernel_size = max(15, min(height, width) // 120)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[tuple[float, float]] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        area = float(cv2.contourArea(contour))
        area_ratio = area / image_area if image_area else 0.0
        if area_ratio < 0.03 or area_ratio > 0.95:
            continue
        (_, _), (rect_width, rect_height), rect_angle = cv2.minAreaRect(contour)
        if rect_width <= 1 or rect_height <= 1:
            continue
        angle = float(rect_angle + 90.0 if rect_width < rect_height else rect_angle)
        angle = _normalize_line_angle(angle)
        if abs(angle) <= 18.0:
            candidates.append((area_ratio, angle))
    if not candidates:
        LOGGER.warning('Receipt preprocessing CONTOUR_ANGLE skipped')
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    area_ratio, angle = candidates[0]
    LOGGER.warning('Receipt preprocessing CONTOUR_ANGLE selected angle=%.2f area_ratio=%.3f', angle, area_ratio)
    if abs(angle) < 0.8:
        return None
    return angle


def _dominant_text_angle(rgb) -> float:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    min_line_length = max(80, max(rgb.shape[:2]) // 8)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=min_line_length, maxLineGap=40)
    if lines is None:
        return 0.0
    accepted_angles = []
    for raw in lines[:, 0, :]:
        x1, y1, x2, y2 = [int(v) for v in raw]
        length = float(np.hypot(x2 - x1, y2 - y1))
        angle = _normalize_line_angle(float(np.degrees(np.arctan2(y2 - y1, x2 - x1))))
        if length >= 80 and abs(angle) <= 18.0:
            accepted_angles.append(angle)
    if not accepted_angles:
        return 0.0
    return float(np.median(accepted_angles))


def _correct_rotation(rgb):
    contour_angle = _dominant_receipt_contour_rotation_angle(rgb)
    if contour_angle is not None:
        applied_angle = -contour_angle
        LOGGER.warning('Receipt preprocessing ROTATION_STAGE method=receipt_contour detected_angle=%.2f applied_angle=%.2f', contour_angle, applied_angle)
        return _rotate_keep_bounds(rgb, applied_angle), contour_angle, applied_angle, True
    angle = _dominant_text_angle(rgb)
    if abs(angle) < 0.8:
        return rgb, angle, 0.0, False
    applied_angle = -angle
    LOGGER.warning('Receipt preprocessing ROTATION_STAGE method=hough_fallback detected_angle=%.2f applied_angle=%.2f', angle, applied_angle)
    return _rotate_keep_bounds(rgb, applied_angle), angle, applied_angle, True


def preprocess_receipt_image_for_ocr(file_bytes: bytes) -> bytes:
    LOGGER.warning('Receipt preprocessing PIPELINE_ENTER variant=deterministic-deskew-v1 bytes=%s', len(file_bytes) if file_bytes else 0)
    if cv2 is None or np is None:
        LOGGER.warning('Receipt preprocessing PIPELINE_ABORT reason=cv2_or_np_missing cv2=%s np=%s', cv2 is not None, np is not None)
        return file_bytes
    try:
        image = Image.open(io.BytesIO(file_bytes))
        image = ImageOps.exif_transpose(image).convert('RGB')
        original = np.array(image)
        rotated, detected_angle, applied_angle, rotation_applied = _correct_rotation(original)
        final = _resize_max_side(rotated)
        _write_debug_png(DEBUG_ORIGINAL_PATH, original, 'deterministic-deskew-v1:original')
        _write_debug_png(DEBUG_ROTATED_PATH, rotated, 'deterministic-deskew-v1:rotated')
        _write_debug_png(DEBUG_FINAL_PATH, final, 'deterministic-deskew-v1:final')
        _write_debug_png(DEBUG_OUTPUT_PATH, final, 'deterministic-deskew-v1:ocr-input-alias')
        LOGGER.warning(
            'Receipt preprocessing PIPELINE_EXIT detected_angle=%.2f applied_angle=%.2f rotation_applied=%s output_shape=%s',
            detected_angle,
            applied_angle,
            rotation_applied,
            _shape_text(final),
        )
        return _encode_png(final)
    except Exception as exc:
        LOGGER.exception('Receipt preprocessing PIPELINE_EXCEPTION error=%s', exc)
        return file_bytes
