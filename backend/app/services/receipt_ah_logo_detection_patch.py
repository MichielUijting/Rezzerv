from __future__ import annotations

import io
import logging
from collections import deque
from typing import Any

from app.services import receipt_service as _receipt_service

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

LOGGER = logging.getLogger(__name__)
_ORIGINAL_PARSE_RECEIPT_CONTENT = getattr(_receipt_service, 'parse_receipt_content', None)
_PHOTO_MIME_TYPES = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp'}
_COMPETING_STORES = {'jumbo', 'lidl', 'plus', 'aldi', 'action', 'gamma', 'hornbach', 'picnic'}


def _looks_like_image_mime(value: Any) -> bool:
    return str(value or '').strip().lower() in _PHOTO_MIME_TYPES


def _has_competing_store(result: Any) -> bool:
    store_text = f"{getattr(result, 'store_name', '') or ''} {getattr(result, 'store_chain', '') or ''}".lower()
    return any(store in store_text for store in _COMPETING_STORES)


def _extract_file_bytes_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[str, bytes | None]:
    if len(args) >= 3 and isinstance(args[2], (bytes, bytearray)):
        return str(args[1] or ''), bytes(args[2])
    if isinstance(kwargs.get('file_bytes'), (bytes, bytearray)):
        return str(kwargs.get('mime_type') or ''), bytes(kwargs.get('file_bytes') or b'')
    return str(kwargs.get('mime_type') or ''), None


def _largest_component(mask: list[list[bool]]) -> int:
    height = len(mask)
    width = len(mask[0]) if height else 0
    seen: set[tuple[int, int]] = set()
    largest = 0
    for y in range(height):
        for x in range(width):
            if not mask[y][x] or (x, y) in seen:
                continue
            queue: deque[tuple[int, int]] = deque([(x, y)])
            seen.add((x, y))
            size = 0
            while queue:
                cx, cy = queue.popleft()
                size += 1
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < width and 0 <= ny < height and mask[ny][nx] and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        queue.append((nx, ny))
            largest = max(largest, size)
    return largest


def _detect_ah_logo_from_bytes(file_bytes: bytes | None) -> bool:
    """Detect the AH logo visually from image content, not filename or OCR text.

    This is deliberately conservative. It looks for a sizeable AH-blue/cyan
    connected component in the receipt header, plus white logo lettering inside
    the same bounding area. The goal is to rescue weak AH photo OCR while not
    turning PLUS/Jumbo/Lidl/ALDI receipts into Albert Heijn.
    """
    if not file_bytes or Image is None:
        return False
    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            rgb = image.convert('RGB')
            rgb.thumbnail((360, 360))
            width, height = rgb.size
            if width < 40 or height < 40:
                return False
            header_height = max(20, int(height * 0.35))
            pixels = rgb.load()

            blue_points: list[tuple[int, int]] = []
            mask: list[list[bool]] = [[False for _ in range(width)] for _ in range(header_height)]
            for y in range(header_height):
                for x in range(width):
                    r, g, b = pixels[x, y]
                    # AH logo cyan/blue: blue-green dominant, not dark navy, not grey.
                    is_ah_blue = b >= 135 and g >= 110 and r <= 80 and (b - r) >= 70 and (g - r) >= 45
                    if is_ah_blue:
                        mask[y][x] = True
                        blue_points.append((x, y))

            if not blue_points:
                return False
            blue_ratio = len(blue_points) / float(width * header_height)
            if blue_ratio < 0.0009 or blue_ratio > 0.08:
                return False
            largest = _largest_component(mask)
            if largest < max(18, int(width * height * 0.00018)):
                return False

            min_x = min(x for x, _ in blue_points)
            max_x = max(x for x, _ in blue_points)
            min_y = min(y for _, y in blue_points)
            max_y = max(y for _, y in blue_points)
            box_w = max_x - min_x + 1
            box_h = max_y - min_y + 1
            if box_w < 10 or box_h < 10:
                return False
            if not (0.55 <= box_w / float(box_h) <= 2.20):
                return False

            # AH logo contains white letters inside the blue shield.
            white_inside = 0
            total_inside = 0
            pad_x = max(1, int(box_w * 0.08))
            pad_y = max(1, int(box_h * 0.08))
            for y in range(max(0, min_y + pad_y), min(header_height, max_y - pad_y + 1)):
                for x in range(max(0, min_x + pad_x), min(width, max_x - pad_x + 1)):
                    r, g, b = pixels[x, y]
                    total_inside += 1
                    if r >= 185 and g >= 185 and b >= 185 and max(r, g, b) - min(r, g, b) <= 55:
                        white_inside += 1
            if total_inside <= 0:
                return False
            white_ratio = white_inside / float(total_inside)
            return 0.03 <= white_ratio <= 0.55
    except Exception as exc:  # pragma: no cover - defensive OCR helper
        LOGGER.debug('ah_logo_detection_failed error=%s', exc)
        return False


def parse_receipt_content(*args: Any, **kwargs: Any):
    if not callable(_ORIGINAL_PARSE_RECEIPT_CONTENT):
        return None
    mime_type, file_bytes = _extract_file_bytes_from_call(args, kwargs)
    ah_logo_detected = _looks_like_image_mime(mime_type) and _detect_ah_logo_from_bytes(file_bytes)
    result = _ORIGINAL_PARSE_RECEIPT_CONTENT(*args, **kwargs)
    if ah_logo_detected and result is not None and getattr(result, 'is_receipt', False):
        if not _has_competing_store(result):
            result.store_name = 'Albert Heijn'
            result.store_branch = getattr(result, 'store_branch', None)
            LOGGER.info('receipt_ah_logo_detected store_name=Albert Heijn')
    return result


def install_receipt_ah_logo_detection_patch(*_: Any) -> bool:
    if getattr(_receipt_service, '_rezzerv_ah_logo_detection_patch_installed', False):
        return False
    _receipt_service.parse_receipt_content = parse_receipt_content
    _receipt_service._detect_ah_logo_from_bytes = _detect_ah_logo_from_bytes
    _receipt_service._rezzerv_ah_logo_detection_patch_installed = True
    LOGGER.info('Receipt AH logo detection patch installed')
    return True


install_receipt_ah_logo_detection_patch()
