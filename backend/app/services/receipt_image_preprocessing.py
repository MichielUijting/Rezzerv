from __future__ import annotations

import io
import logging

from PIL import Image, ImageOps

LOGGER = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    from deskew import determine_skew
except Exception:
    cv2 = None
    np = None
    determine_skew = None


def _encode_png(arr) -> bytes:
    out = Image.fromarray(arr)
    buffer = io.BytesIO()
    out.save(buffer, format="PNG")
    return buffer.getvalue()


def _rotate_image(arr, angle):
    if cv2 is None or np is None:
        return arr
    try:
        (h, w) = arr.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(arr, matrix, (w, h), borderValue=(255, 255, 255))
        return rotated
    except Exception:
        return arr


def preprocess_receipt_image_for_ocr(file_bytes: bytes) -> bytes:
    LOGGER.warning("Receipt preprocessing: module entered")

    if cv2 is None or np is None or determine_skew is None:
        LOGGER.warning(f"Receipt preprocessing: dependencies missing cv2={cv2 is not None}, np={np is not None}, deskew={determine_skew is not None}")
        return file_bytes

    try:
        image = Image.open(io.BytesIO(file_bytes))
        image = ImageOps.exif_transpose(image).convert("RGB")
        arr = np.array(image)

        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        angle = determine_skew(gray)
        LOGGER.warning(f"Receipt preprocessing: detected angle={angle}")

        if angle is None or abs(angle) < 1.0:
            LOGGER.warning("Receipt preprocessing: skipped (angle too small or None)")
            return file_bytes

        applied_angle = -float(angle)
        rotated = _rotate_image(arr, applied_angle)

        if rotated is None:
            return file_bytes

        LOGGER.warning(f"Receipt preprocessing: applied rotation angle={applied_angle}")
        return _encode_png(rotated)

    except Exception as exc:
        LOGGER.warning("Deskew preprocessing skipped: %s", exc)
        return file_bytes
