from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image, ImageOps

LOGGER = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

DEBUG_OUTPUT_PATH = Path('/app/data/receipts/debug/latest-ocr-preprocessed.png')


def _encode_png(rgb) -> bytes:
    image = Image.fromarray(rgb)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def _save_debug_image(rgb, reason: str) -> None:
    try:
        DEBUG_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEBUG_OUTPUT_PATH.write_bytes(_encode_png(rgb))
        LOGGER.warning('Receipt preprocessing: debug image saved path=%s reason=%s', DEBUG_OUTPUT_PATH, reason)
    except Exception as exc:
        LOGGER.warning('Receipt preprocessing: debug image save failed: %s', exc)


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


def _dominant_text_angle(rgb) -> float:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=max(80, max(rgb.shape[:2]) // 8), maxLineGap=40)
    if lines is None:
        LOGGER.warning('Receipt preprocessing: rotation skipped no hough lines')
        return 0.0

    angles = []
    for raw in lines[:, 0, :]:
        x1, y1, x2, y2 = [int(v) for v in raw]
        length = float(np.hypot(x2 - x1, y2 - y1))
        if length < 80:
            continue
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        while angle <= -90:
            angle += 180
        while angle > 90:
            angle -= 180
        if abs(angle) <= 60:
            angles.append(angle)

    if not angles:
        LOGGER.warning('Receipt preprocessing: rotation skipped no usable line angles')
        return 0.0

    median_angle = float(np.median(angles))
    LOGGER.warning('Receipt preprocessing: detected rotation angle=%.2f line_count=%s', median_angle, len(angles))
    return median_angle


def _correct_rotation(rgb):
    angle = _dominant_text_angle(rgb)
    if abs(angle) < 2.0:
        LOGGER.warning('Receipt preprocessing: rotation not applied angle=%.2f', angle)
        return rgb
    applied_angle = -angle
    LOGGER.warning('Receipt preprocessing: rotation applied angle=%.2f', applied_angle)
    return _rotate_keep_bounds(rgb, applied_angle)


def _order_points(pts):
    rect = np.zeros((4, 2), dtype='float32')
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _warp_if_receipt_detected(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

    for contour in contours:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) != 4:
            continue

        points = approx.reshape(4, 2).astype('float32')
        rect = _order_points(points)
        tl, tr, br, bl = rect
        max_width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
        max_height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
        if max_width < 250 or max_height < 250:
            continue

        dst = np.array([[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]], dtype='float32')
        matrix = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(rgb, matrix, (max_width, max_height), borderValue=(255, 255, 255))
        LOGGER.warning('Receipt preprocessing: perspective warp applied width=%s height=%s', max_width, max_height)
        return warped

    LOGGER.warning('Receipt preprocessing: perspective warp skipped no receipt contour')
    return rgb


def preprocess_receipt_image_for_ocr(file_bytes: bytes) -> bytes:
    LOGGER.warning('Receipt preprocessing: module entered (clean rotation-first)')
    if cv2 is None or np is None:
        LOGGER.warning('Receipt preprocessing: cv2/np missing')
        return file_bytes

    try:
        image = Image.open(io.BytesIO(file_bytes))
        image = ImageOps.exif_transpose(image).convert('RGB')
        rgb = np.array(image)

        rotated = _correct_rotation(rgb)
        result = _warp_if_receipt_detected(rotated)

        _save_debug_image(result, 'clean-rotation-first')
        return _encode_png(result)
    except Exception as exc:
        LOGGER.warning('Clean rotation-first preprocessing failed: %s', exc)
        return file_bytes
