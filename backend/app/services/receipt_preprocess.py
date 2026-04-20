from __future__ import annotations

import io
import logging
from typing import Any

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except Exception:  # pragma: no cover
    Image = None
    ImageEnhance = None
    ImageFilter = None
    ImageOps = None

LOGGER = logging.getLogger(__name__)

SUPPORTED_IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp'}


def _pil_normalize(image: Any) -> Any:
    if ImageOps is not None:
        image = ImageOps.exif_transpose(image)
        image = ImageOps.autocontrast(image)
    if ImageEnhance is not None:
        image = ImageEnhance.Contrast(image).enhance(1.2)
        image = ImageEnhance.Sharpness(image).enhance(1.15)
    if ImageFilter is not None:
        image = image.filter(ImageFilter.MedianFilter(size=3))
    return image.convert('L')


def _cv2_order_points(pts: Any) -> Any:
    rect = np.zeros((4, 2), dtype='float32')
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _cv2_warp(image: Any, pts: Any) -> Any:
    rect = _cv2_order_points(pts)
    tl, tr, br, bl = rect
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = max(int(width_a), int(width_b))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = max(int(height_a), int(height_b))
    if max_width < 40 or max_height < 40:
        raise ValueError('receipt contour too small')
    dst = np.array(
        [[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]],
        dtype='float32',
    )
    matrix = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, matrix, (max_width, max_height))


def _cv2_detect_and_warp(image_bgr: Any) -> tuple[Any, dict[str, Any]]:
    debug: dict[str, Any] = {'cropped': False, 'deskew_angle': 0.0}
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 60, 180)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(gray.shape[0] * gray.shape[1])
    best = None
    best_score = -1.0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * 0.1:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = h / max(w, 1)
        area_ratio = area / image_area
        score = area_ratio + (0.35 if len(approx) == 4 else 0.0) + (0.15 if aspect_ratio > 1.2 else 0.0)
        if score > best_score:
            best_score = score
            best = approx if len(approx) == 4 else cv2.boxPoints(cv2.minAreaRect(contour))
    working = image_bgr
    if best is not None:
        pts = np.asarray(best, dtype='float32').reshape(4, 2)
        working = _cv2_warp(image_bgr, pts)
        debug['cropped'] = True

    gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
    inv = cv2.bitwise_not(gray)
    _, th = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    coords = cv2.findNonZero(th)
    if coords is not None:
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        if angle < -45:
            angle = 90 + angle
        elif angle > 45:
            angle = angle - 90
        if abs(angle) >= 0.5:
            h, w = working.shape[:2]
            center = (w // 2, h // 2)
            matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
            working = cv2.warpAffine(
                working,
                matrix,
                (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
            debug['deskew_angle'] = round(float(angle), 3)

    normalized = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
    normalized = cv2.equalizeHist(normalized)
    normalized = cv2.GaussianBlur(normalized, (0, 0), 1.2)
    normalized = cv2.addWeighted(cv2.cvtColor(working, cv2.COLOR_BGR2GRAY), 1.4, normalized, -0.4, 0)
    return normalized, debug


def isolate_receipt_image(file_bytes: bytes, filename: str | None = None) -> dict[str, Any]:
    debug: dict[str, Any] = {
        'success': False,
        'used_fallback': False,
        'cropped': False,
        'deskew_angle': 0.0,
        'filename': filename,
    }
    if not file_bytes:
        debug['error'] = 'empty_file'
        return {'success': False, 'image_bytes': file_bytes, 'debug': debug}

    if Image is None:
        debug['error'] = 'pillow_unavailable'
        debug['used_fallback'] = True
        return {'success': False, 'image_bytes': file_bytes, 'debug': debug}

    try:
        with Image.open(io.BytesIO(file_bytes)) as pil_image:
            pil_image.load()
            normalized_image = None
            if cv2 is not None and np is not None:
                try:
                    image_bgr = cv2.imdecode(np.frombuffer(file_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if image_bgr is not None:
                        gray, cv2_debug = _cv2_detect_and_warp(image_bgr)
                        normalized_image = Image.fromarray(gray)
                        debug.update(cv2_debug)
                except Exception as exc:  # pragma: no cover
                    LOGGER.warning('Receipt CV preprocess fallback voor %s: %s', filename or '<memory>', exc)
                    debug['cv2_error'] = str(exc)
            if normalized_image is None:
                normalized_image = _pil_normalize(pil_image)
                debug['used_fallback'] = True

            output = io.BytesIO()
            normalized_image.save(output, format='PNG')
            debug['success'] = True
            return {
                'success': True,
                'image_bytes': output.getvalue(),
                'debug': debug,
            }
    except Exception as exc:
        debug['error'] = str(exc)
        debug['used_fallback'] = True
        return {'success': False, 'image_bytes': file_bytes, 'debug': debug}
