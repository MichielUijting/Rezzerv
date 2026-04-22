from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .receipt_photo_types import ReceiptNormalizationResult


PHOTO_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png"}


class ReceiptPhotoNormalizer:
    def normalize(self, image_path: str, mime_type: str | None = None) -> ReceiptNormalizationResult:
        original_path = image_path

        if not image_path or not Path(image_path).exists():
            return ReceiptNormalizationResult(False, True, 0.0, "file_not_found", False, original_path, None, None)

        detected_as_photo = mime_type in PHOTO_MIME_TYPES if mime_type else image_path.lower().endswith((".jpg", ".jpeg", ".png"))

        if not detected_as_photo:
            return ReceiptNormalizationResult(False, True, 0.0, "not_photo", False, original_path, None, None)

        try:
            image = cv2.imread(image_path)
            if image is None:
                return ReceiptNormalizationResult(False, True, 0.0, "cv2_read_failed", True, original_path, None, None)

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edged = cv2.Canny(blurred, 50, 150)

            contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

            receipt_contour = None
            for c in contours:
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.02 * peri, True)
                if len(approx) == 4:
                    receipt_contour = approx
                    break

            if receipt_contour is None:
                return ReceiptNormalizationResult(False, True, 0.2, "no_contour", True, original_path, None, None)

            pts = receipt_contour.reshape(4, 2)
            rect = self._order_points(pts)

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
                [0, maxHeight - 1],
            ], dtype="float32")

            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))

            if warped.shape[0] < warped.shape[1]:
                warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)

            gray_warped = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
            ocr_ready = cv2.adaptiveThreshold(gray_warped, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)

            tmp_dir = tempfile.mkdtemp(prefix="rezzerv_norm_")
            normalized_path = str(Path(tmp_dir) / "normalized.png")
            ocr_ready_path = str(Path(tmp_dir) / "ocr_ready.png")

            cv2.imwrite(normalized_path, warped)
            cv2.imwrite(ocr_ready_path, ocr_ready)

            confidence = 0.8

            return ReceiptNormalizationResult(True, False, confidence, None, True, original_path, normalized_path, ocr_ready_path)

        except Exception as e:
            return ReceiptNormalizationResult(False, True, 0.0, f"exception:{e}", True, original_path, None, None)

    def _order_points(self, pts):
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]

        return rect
