from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np

from .receipt_photo_types import ReceiptNormalizationResult


PHOTO_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png"}
MAX_WORKING_DIMENSION = 1800
MIN_RECEIPT_AREA_RATIO = 0.08


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

            working, scale = self._resize_for_processing(image)
            warped, contour_confidence, contour_reason = self._try_perspective_crop(working)
            used_fallback = False

            if warped is None:
                used_fallback = True
                warped, fallback_confidence, fallback_reason = self._deskew_fallback(working)
                contour_confidence = fallback_confidence
                contour_reason = fallback_reason

            if warped is None:
                return ReceiptNormalizationResult(False, True, 0.15, contour_reason or "normalization_failed", True, original_path, None, None)

            if warped.shape[0] < warped.shape[1]:
                warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)

            enhanced = self._enhance_for_storage(warped)
            ocr_ready = self._make_ocr_ready(warped)

            tmp_dir = tempfile.mkdtemp(prefix="rezzerv_norm_")
            normalized_path = str(Path(tmp_dir) / "normalized.png")
            ocr_ready_path = str(Path(tmp_dir) / "ocr_ready.png")

            cv2.imwrite(normalized_path, enhanced)
            cv2.imwrite(ocr_ready_path, ocr_ready)

            confidence = max(0.25, min(0.92, contour_confidence))
            reason = contour_reason if used_fallback else None

            return ReceiptNormalizationResult(
                True,
                used_fallback,
                confidence,
                reason,
                True,
                original_path,
                normalized_path,
                ocr_ready_path,
            )

        except Exception as e:
            return ReceiptNormalizationResult(False, True, 0.0, f"exception:{e}", True, original_path, None, None)

    def _resize_for_processing(self, image):
        height, width = image.shape[:2]
        largest = max(height, width)
        if largest <= MAX_WORKING_DIMENSION:
            return image.copy(), 1.0
        scale = MAX_WORKING_DIMENSION / float(largest)
        resized = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
        return resized, scale

    def _try_perspective_crop(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = self._shadow_correct(gray)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 40, 140)
        edged = cv2.dilate(edged, np.ones((3, 3), np.uint8), iterations=1)

        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, 0.2, "no_contours"

        image_area = float(image.shape[0] * image.shape[1])
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:12]

        best_rect = None
        best_area = 0.0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area / image_area < MIN_RECEIPT_AREA_RATIO:
                continue

            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
            if len(approx) == 4:
                candidate = approx.reshape(4, 2).astype("float32")
            else:
                rect = cv2.minAreaRect(contour)
                candidate = cv2.boxPoints(rect).astype("float32")

            ordered = self._order_points(candidate)
            width_a = np.linalg.norm(ordered[2] - ordered[3])
            width_b = np.linalg.norm(ordered[1] - ordered[0])
            height_a = np.linalg.norm(ordered[1] - ordered[2])
            height_b = np.linalg.norm(ordered[0] - ordered[3])
            max_width = max(width_a, width_b)
            max_height = max(height_a, height_b)
            if min(max_width, max_height) < 80:
                continue
            aspect = max(max_width, max_height) / max(1.0, min(max_width, max_height))
            if aspect < 1.5:
                continue
            if area > best_area:
                best_area = area
                best_rect = ordered

        if best_rect is None:
            return None, 0.25, "no_receipt_contour"

        warped = self._four_point_transform(image, best_rect)
        area_ratio = best_area / image_area
        confidence = 0.58 + min(0.3, area_ratio)
        return warped, confidence, None

    def _deskew_fallback(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corrected = self._shadow_correct(gray)
        binary = cv2.threshold(corrected, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        binary_inv = 255 - binary

        coords = cv2.findNonZero(binary_inv)
        if coords is None:
            return image.copy(), 0.25, "fallback_no_text"

        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        if angle < -45:
            angle = 90 + angle
        elif angle > 45:
            angle = angle - 90

        height, width = image.shape[:2]
        center = (width // 2, height // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(image, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        cropped = self._crop_foreground(rotated)
        return cropped, 0.42, f"fallback_deskew:{round(float(angle), 2)}"

    def _crop_foreground(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corrected = self._shadow_correct(gray)
        binary = cv2.threshold(corrected, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        foreground = 255 - binary
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return image
        contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(contour)
        margin = max(12, int(min(image.shape[:2]) * 0.02))
        x0 = max(0, x - margin)
        y0 = max(0, y - margin)
        x1 = min(image.shape[1], x + w + margin)
        y1 = min(image.shape[0], y + h + margin)
        if (x1 - x0) < 120 or (y1 - y0) < 120:
            return image
        return image[y0:y1, x0:x1]

    def _enhance_for_storage(self, image):
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_channel = clahe.apply(l_channel)
        merged = cv2.merge((l_channel, a_channel, b_channel))
        return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

    def _make_ocr_ready(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = self._shadow_correct(gray)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        gray = cv2.fastNlMeansDenoising(gray, None, 12, 7, 21)
        block_size = max(31, int(min(gray.shape[:2]) / 25))
        if block_size % 2 == 0:
            block_size += 1
        block_size = min(block_size, 91)
        ocr_ready = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            block_size,
            11,
        )
        return ocr_ready

    def _shadow_correct(self, gray):
        kernel_size = max(31, int(min(gray.shape[:2]) / 18))
        if kernel_size % 2 == 0:
            kernel_size += 1
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
        corrected = cv2.divide(gray, background, scale=255)
        return corrected

    def _four_point_transform(self, image, rect):
        (tl, tr, br, bl) = rect
        width_a = np.linalg.norm(br - bl)
        width_b = np.linalg.norm(tr - tl)
        max_width = int(max(width_a, width_b))

        height_a = np.linalg.norm(tr - br)
        height_b = np.linalg.norm(tl - bl)
        max_height = int(max(height_a, height_b))

        dst = np.array([
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ], dtype="float32")

        matrix = cv2.getPerspectiveTransform(rect, dst)
        return cv2.warpPerspective(image, matrix, (max_width, max_height))

    def _order_points(self, pts):
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]

        return rect
