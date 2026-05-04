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


def _encode_png(arr) -> bytes:
    out = Image.fromarray(arr)
    buffer = io.BytesIO()
    out.save(buffer, format="PNG")
    return buffer.getvalue()


def _save_debug_image(image_bytes: bytes, reason: str) -> None:
    try:
        DEBUG_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEBUG_OUTPUT_PATH.write_bytes(image_bytes)
        LOGGER.warning("Receipt preprocessing: debug image saved path=%s reason=%s", DEBUG_OUTPUT_PATH, reason)
    except Exception as exc:
        LOGGER.warning("Receipt preprocessing: debug image save failed: %s", exc)


def _order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _four_point_transform(image, pts):
    rect = _order_points(pts)
    (tl, tr, br, bl) = rect
    max_width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    max_height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if max_width < 300 or max_height < 300:
        return None
    dst = np.array([[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]], dtype="float32")
    matrix = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, matrix, (max_width, max_height), borderValue=(255, 255, 255))


def _valid_contour(contour, approx, image_shape) -> bool:
    ih, iw = image_shape[:2]
    image_area = float(iw * ih)
    area = float(cv2.contourArea(contour))
    ratio_area = area / image_area if image_area else 0.0
    if ratio_area < 0.08 or ratio_area > 0.95:
        LOGGER.warning("Receipt preprocessing: contour rejected area_ratio=%.3f", ratio_area)
        return False
    x, y, w, h = cv2.boundingRect(approx)
    if w < 300 or h < 300:
        LOGGER.warning("Receipt preprocessing: contour rejected box=%sx%s", w, h)
        return False
    aspect = max(float(w) / float(h), float(h) / float(w))
    if aspect < 1.4:
        LOGGER.warning("Receipt preprocessing: contour rejected aspect=%.3f", aspect)
        return False
    return True


def _valid_warp(warped) -> bool:
    if warped is None:
        return False
    h, w = warped.shape[:2]
    if w < 300 or h < 300:
        return False
    gray = cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)
    mean = float(np.mean(gray))
    std = float(np.std(gray))
    dark_ratio = float(np.mean(gray < 50))
    light_ratio = float(np.mean(gray > 180))
    if mean < 45 or mean > 245 or std < 10 or dark_ratio > 0.80 or light_ratio < 0.05:
        LOGGER.warning("Receipt preprocessing: warp rejected mean=%.2f std=%.2f dark=%.3f light=%.3f", mean, std, dark_ratio, light_ratio)
        return False
    return True


def preprocess_receipt_image_for_ocr(file_bytes: bytes) -> bytes:
    LOGGER.warning("Receipt preprocessing: module entered (rectifier)")
    if cv2 is None or np is None:
        LOGGER.warning("Receipt preprocessing: cv2/np missing")
        _save_debug_image(file_bytes, 'fallback-dependencies-missing')
        return file_bytes
    try:
        image = Image.open(io.BytesIO(file_bytes))
        image = ImageOps.exif_transpose(image).convert("RGB")
        arr = np.array(image)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blur, 50, 150)
        contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        for index, contour in enumerate(contours[:12]):
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
            if len(approx) != 4:
                continue
            if not _valid_contour(contour, approx, arr.shape):
                continue
            warped = _four_point_transform(arr, approx.reshape(4, 2))
            if not _valid_warp(warped):
                continue
            LOGGER.warning("Receipt preprocessing: valid 4-point contour selected index=%s", index)
            result = _encode_png(warped)
            _save_debug_image(result, 'rectified-validated-4-point-contour')
            return result
        LOGGER.warning("Receipt preprocessing: fallback (no valid contour)")
        _save_debug_image(file_bytes, 'fallback-no-valid-contour')
        return file_bytes
    except Exception as exc:
        LOGGER.warning("Rectifier preprocessing failed: %s", exc)
        _save_debug_image(file_bytes, 'fallback-exception')
        return file_bytes
