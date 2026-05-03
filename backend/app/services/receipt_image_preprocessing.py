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

            out = Image.fromarray(warped)
            buffer = io.BytesIO()
            out.save(buffer, format="PNG")
            return buffer.getvalue()

        return file_bytes
    except Exception as exc:
        LOGGER.warning("Receipt image preprocessing skipped: %s", exc)
        return file_bytes
