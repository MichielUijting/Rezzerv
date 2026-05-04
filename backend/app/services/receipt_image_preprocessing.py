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

    widthA = np.linalg.norm(br - bl)
    widthB = np.linalg.norm(tr - tl)
    maxWidth = int(max(widthA, widthB))

    heightA = np.linalg.norm(tr - br)
    heightB = np.linalg.norm(tl - bl)
    maxHeight = int(max(heightA, heightB))

    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))

    return warped


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

        for c in contours[:5]:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)

            if len(approx) == 4:
                LOGGER.warning("Receipt preprocessing: 4-point contour found")
                warped = _four_point_transform(arr, approx.reshape(4, 2))
                result = _encode_png(warped)
                _save_debug_image(result, 'rectified-4-point-contour')
                return result

        LOGGER.warning("Receipt preprocessing: fallback (no contour)")
        _save_debug_image(file_bytes, 'fallback-no-contour')
        return file_bytes

    except Exception as exc:
        LOGGER.warning("Rectifier preprocessing failed: %s", exc)
        _save_debug_image(file_bytes, 'fallback-exception')
        return file_bytes
