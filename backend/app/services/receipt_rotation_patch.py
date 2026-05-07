from __future__ import annotations

import io
import math
import re
import tempfile
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from app.services import receipt_service

try:
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover
    Image = None
    ImageOps = None


_ORIGINAL_PARSE_RECEIPT_CONTENT = receipt_service.parse_receipt_content
_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
_MAX_DESKEW_DEGREES = 12.0
_MIN_DESKEW_DEGREES = 0.8
_PRICE_RE = re.compile(r'-?\d{1,6}[\.,]\d{2}')


def _is_image_receipt(filename: str | None, mime_type: str | None) -> bool:
    name = str(filename or '').lower()
    mime = str(mime_type or '').lower()
    return name.endswith(_IMAGE_EXTENSIONS) or mime.startswith('image/')


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except Exception:
        return None


def _sum_lines(lines: list[dict[str, Any]] | None) -> Decimal | None:
    total = Decimal('0.00')
    found = False
    for line in lines or []:
        amount = _to_decimal(line.get('line_total') if isinstance(line, dict) else None)
        if amount is None:
            continue
        total += amount
        found = True
    return total.quantize(Decimal('0.01')) if found else None


def _looks_suspicious(result: Any) -> bool:
    lines = list(getattr(result, 'lines', None) or [])
    if not lines:
        return False
    total = _to_decimal(getattr(result, 'total_amount', None))
    line_sum = _sum_lines(lines)
    if total is not None and line_sum is not None and abs(total - line_sum) > Decimal('0.01'):
        return True
    for line in lines:
        if not isinstance(line, dict):
            continue
        label = str(line.get('normalized_label') or line.get('raw_label') or '').strip()
        compact = re.sub(r'\s+', ' ', label.upper())
        if 'CHAUDF WATER AH SANDWICH' in compact:
            return True
        if len(label) > 38 and not _PRICE_RE.search(label):
            return True
    return False


def _box_angle_degrees(box: Any) -> float | None:
    try:
        points = [(float(point[0]), float(point[1])) for point in box]
    except Exception:
        return None
    if len(points) < 4:
        return None
    left_top, right_top = points[0], points[1]
    dx = right_top[0] - left_top[0]
    dy = right_top[1] - left_top[1]
    if abs(dx) < 3:
        return None
    angle = math.degrees(math.atan2(dy, dx))
    while angle <= -45:
        angle += 90
    while angle > 45:
        angle -= 90
    return angle


def _extract_ocr_items(raw_ocr: Any) -> list[tuple[Any, str]]:
    items: list[tuple[Any, str]] = []
    if raw_ocr is None:
        return items
    pages = raw_ocr if isinstance(raw_ocr, list) else [raw_ocr]
    for page in pages:
        if page is None:
            continue
        for row in page:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            box = row[0]
            text_part = row[1]
            text = ''
            if isinstance(text_part, (list, tuple)) and text_part:
                text = str(text_part[0] or '')
            else:
                text = str(text_part or '')
            if text.strip():
                items.append((box, text.strip()))
    return items


def _ocr_items_for_angle(file_bytes: bytes) -> list[tuple[Any, str]]:
    if Image is None or ImageOps is None or receipt_service.PaddleOCR is None:
        return []
    ocr = receipt_service._get_paddle_ocr()
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                ImageOps.exif_transpose(img).convert('RGB').save(tmp, format='PNG')
            raw = ocr.ocr(str(tmp_path), cls=True)
            return _extract_ocr_items(raw)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


def _measured_text_angle(file_bytes: bytes) -> float | None:
    items = _ocr_items_for_angle(file_bytes)
    angles: list[float] = []
    for box, text in items:
        if len(text) < 2:
            continue
        angle = _box_angle_degrees(box)
        if angle is None:
            continue
        if abs(angle) <= _MAX_DESKEW_DEGREES:
            angles.append(angle)
    if len(angles) < 3:
        return None
    measured = float(median(angles))
    if abs(measured) < _MIN_DESKEW_DEGREES:
        return None
    return measured


def _rotate_image_bytes(file_bytes: bytes, filename: str, degrees: float) -> tuple[bytes, str] | None:
    if Image is None or ImageOps is None:
        return None
    try:
        with Image.open(io.BytesIO(file_bytes)) as img:
            img = ImageOps.exif_transpose(img).convert('RGB')
            rotated = img.rotate(degrees, expand=True, fillcolor='white')
            output = io.BytesIO()
            rotated.save(output, format='PNG', optimize=True)
            return output.getvalue(), f'{filename or "receipt"}.deskew-measured-{degrees:+.2f}.png'
    except Exception:
        return None


def _annotate_result(result: Any, measured_angle: float | None, applied_rotation: float | None, reason: str) -> Any:
    try:
        setattr(result, 'rotation_measured_text_angle', measured_angle)
        setattr(result, 'rotation_applied_degrees', applied_rotation)
        setattr(result, 'rotation_selection_reason', reason)
        setattr(result, 'rotation_candidates_tried', 1 if applied_rotation is not None else 0)
        for line in list(getattr(result, 'lines', None) or []):
            if isinstance(line, dict):
                line.setdefault('rotation_measured_text_angle', measured_angle)
                line.setdefault('rotation_applied_degrees', applied_rotation)
    except Exception:
        pass
    return result


def parse_receipt_content(file_bytes: bytes, filename: str, mime_type: str | None = None):
    if not _is_image_receipt(filename, mime_type):
        return _ORIGINAL_PARSE_RECEIPT_CONTENT(file_bytes, filename, mime_type)
    if Image is None or ImageOps is None:
        return _ORIGINAL_PARSE_RECEIPT_CONTENT(file_bytes, filename, mime_type)

    measured_angle = _measured_text_angle(file_bytes)
    if measured_angle is None:
        result = _ORIGINAL_PARSE_RECEIPT_CONTENT(file_bytes, filename, mime_type)
        return _annotate_result(result, None, None, 'no_reliable_text_angle')

    # Pillow rotate is counter-clockwise for positive degrees. To deskew a text baseline
    # measured at +theta degrees, rotate by -theta once. No trial-and-error candidates.
    applied_rotation = -measured_angle
    rotated = _rotate_image_bytes(file_bytes, filename, applied_rotation)
    if rotated is None:
        result = _ORIGINAL_PARSE_RECEIPT_CONTENT(file_bytes, filename, mime_type)
        return _annotate_result(result, measured_angle, None, 'rotation_failed')

    rotated_bytes, rotated_filename = rotated
    rotated_result = _ORIGINAL_PARSE_RECEIPT_CONTENT(rotated_bytes, rotated_filename, 'image/png')

    # SSOT safety: if the measured correction does not improve a suspicious parse, keep
    # the original output instead of forcing a lower-quality repair.
    original_result = _ORIGINAL_PARSE_RECEIPT_CONTENT(file_bytes, filename, mime_type)
    if _looks_suspicious(rotated_result) and not _looks_suspicious(original_result):
        return _annotate_result(original_result, measured_angle, None, 'measured_rotation_rejected_by_safety_check')
    return _annotate_result(rotated_result, measured_angle, applied_rotation, 'measured_text_angle')


def install_receipt_rotation_patch(*_: Any) -> bool:
    receipt_service.parse_receipt_content = parse_receipt_content
    return True


install_receipt_rotation_patch()
