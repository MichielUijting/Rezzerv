from __future__ import annotations

import io
import logging

from PIL import Image, ImageOps

LOGGER = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None


def _encode_png(arr) -> bytes:
    out = Image.fromarray(arr)
    buffer = io.BytesIO()
    out.save(buffer, format="PNG")
    return buffer.getvalue()


def _looks_safe_for_ocr(original_arr, candidate_arr) -> bool:
    if cv2 is None or np is None:
        return False

    try:
        original_area = int(original_arr.shape[0]) * int(original_arr.shape[1])
        candidate_area = int(candidate_arr.shape[0]) * int(candidate_arr.shape[1])
        if original_area <= 0 or candidate_area <= 0:
            return False

        # Een te agressieve crop levert vaak een klein, donker fragment op.
        if candidate_area < original_area * 0.20:
            return False

        if min(candidate_arr.shape[0], candidate_arr.shape[1]) < 300:
            return False

        gray = cv2.cvtColor(candidate_arr, cv2.COLOR_RGB2GRAY)
        mean_brightness = float(np.mean(gray))
        white_ratio = float(np.mean(gray > 180))
        dark_ratio = float(np.mean(gray < 35))

        if mean_brightness < 70:
            return False
        if white_ratio < 0.15:
            return False
        if dark_ratio > 0.70:
            return False

        return True
    except Exception:
        return False


def preprocess_receipt_image_for_ocr(file_bytes: bytes) -> bytes:
    if cv2 is None or np is None:
        return file_bytes

    try:
        image = Image.open(io.BytesIO(file_bytes))
        image = ImageOps.exif_transpose(image).convert("RGB")
        arr = np.array(image)

        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return file_bytes

        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        image_area = arr.shape[0] * arr.shape[1]

        for contour in contours[:5]:
            area = cv2.contourArea(contour)
            if area < image_area * 0.15:
                continue

            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
            if len(approx) != 4:
                continue

            pts = approx.reshape(4, 2).astype("float32")
            s = pts.sum(axis=1)
            diff = np.diff(pts, axis=1)

            rect = np.array([
                pts[np.argmin(s)],
                pts[np.argmin(diff)],
                pts[np.argmax(s)],
                pts[np.argmax(diff)],
            ], dtype="float32")

            (tl, tr, br, bl) = rect
            width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
            height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))

            if width < 300 or height < 300:
                continue

            dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
            matrix = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(arr, matrix, (width, height))

            if width > height:
                warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)

            if not _looks_safe_for_ocr(arr, warped):
                LOGGER.info("Receipt image preprocessing fallback: candidate failed quality checks")
                return file_bytes

            return _encode_png(warped)

        return file_bytes
    except Exception as exc:
        LOGGER.warning("Receipt image preprocessing skipped: %s", exc)
        return file_bytes
