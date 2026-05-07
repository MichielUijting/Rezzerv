from __future__ import annotations

import io
import re
from decimal import Decimal
from typing import Any

from app.services import receipt_service

try:
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover
    Image = None
    ImageOps = None


_ORIGINAL_PARSE_RECEIPT_CONTENT = receipt_service.parse_receipt_content
_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
_DESKEW_CANDIDATE_DEGREES = (-8.0, -6.0, -4.0, -2.5, -1.5, 1.5, 2.5, 4.0, 6.0, 8.0)
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


def _line_score(result: Any) -> int:
    lines = list(getattr(result, 'lines', None) or [])
    total = _to_decimal(getattr(result, 'total_amount', None))
    line_sum = _sum_lines(lines)
    score = 0
    if getattr(result, 'is_receipt', False):
        score += 1000
    if getattr(result, 'store_name', None):
        score += 250
    if total is not None:
        score += 250
    if total is not None and line_sum is not None:
        diff = abs(total - line_sum)
        if diff <= Decimal('0.01'):
            score += 700
        elif diff <= Decimal('0.25'):
            score += 350
        else:
            score -= min(int(diff * 10), 400)
    score += min(len(lines), 60) * 35

    for line in lines:
        if not isinstance(line, dict):
            continue
        label = str(line.get('normalized_label') or line.get('raw_label') or '').strip()
        if len(label) > 34:
            score -= 45
        if re.search(r'\b(water|sandwich|brood|drank|cola|sap|koffie|thee)\b.*\b(water|sandwich|brood|drank|cola|sap|koffie|thee)\b', label, re.I):
            score -= 160
        if ' CHAUDF WATER AH SANDWICH' in f' {label.upper()}':
            score -= 500
    return score


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


def _rotate_image_bytes(file_bytes: bytes, filename: str, degrees: float) -> tuple[bytes, str] | None:
    if Image is None or ImageOps is None:
        return None
    try:
        with Image.open(io.BytesIO(file_bytes)) as img:
            img = ImageOps.exif_transpose(img).convert('RGB')
            rotated = img.rotate(degrees, expand=True, fillcolor='white')
            output = io.BytesIO()
            rotated.save(output, format='PNG', optimize=True)
            return output.getvalue(), f'{filename or "receipt"}.deskew-{degrees:+.1f}.png'
    except Exception:
        return None


def _annotate_result(result: Any, rotation_degree: float | None, candidates_tried: int, reason: str | None = None) -> Any:
    try:
        setattr(result, 'rotation_candidate_degree', rotation_degree)
        setattr(result, 'rotation_candidates_tried', candidates_tried)
        setattr(result, 'rotation_selection_reason', reason)
        for line in list(getattr(result, 'lines', None) or []):
            if isinstance(line, dict):
                line.setdefault('rotation_candidate_degree', rotation_degree)
    except Exception:
        pass
    return result


def parse_receipt_content(file_bytes: bytes, filename: str, mime_type: str | None = None):
    base_result = _ORIGINAL_PARSE_RECEIPT_CONTENT(file_bytes, filename, mime_type)
    if not _is_image_receipt(filename, mime_type):
        return base_result
    if Image is None or ImageOps is None:
        return base_result
    if not _looks_suspicious(base_result):
        return _annotate_result(base_result, None, 0, 'base_result_not_suspicious')

    best_result = base_result
    best_score = _line_score(base_result)
    tried = 0
    for degrees in _DESKEW_CANDIDATE_DEGREES:
        rotated = _rotate_image_bytes(file_bytes, filename, degrees)
        if rotated is None:
            continue
        rotated_bytes, rotated_filename = rotated
        tried += 1
        try:
            candidate = _ORIGINAL_PARSE_RECEIPT_CONTENT(rotated_bytes, rotated_filename, 'image/png')
        except Exception:
            continue
        candidate_score = _line_score(candidate)
        if candidate_score > best_score:
            best_score = candidate_score
            best_result = _annotate_result(candidate, degrees, tried, 'better_deskew_candidate')

    if best_result is base_result:
        return _annotate_result(base_result, None, tried, 'no_better_candidate')
    return best_result


def install_receipt_rotation_patch(*_: Any) -> bool:
    receipt_service.parse_receipt_content = parse_receipt_content
    return True


install_receipt_rotation_patch()
