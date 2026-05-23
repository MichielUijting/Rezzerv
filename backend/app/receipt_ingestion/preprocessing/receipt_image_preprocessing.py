from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

from app.receipt_ingestion.preprocessing.perspective_normalization import normalize_receipt_perspective_image

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
LANDSCAPE_ASPECT_LIMIT = 1.20
MIN_FOREGROUND_AREA_RATIO = 0.05


@dataclass
class ReceiptImagePreprocessingDecision:
    preprocessing_step: str
    selected_route: str
    applied_steps: list[str]
    fallback_reason: list[str]
    perspective_normalization: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _decode_image(file_bytes: bytes):
    if cv2 is None or np is None:
        return None
    data = np.frombuffer(file_bytes, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _encode_image_png(image) -> bytes | None:
    if cv2 is None:
        return None
    ok, encoded = cv2.imencode(".png", image)
    return bytes(encoded.tobytes()) if ok else None


def _rotate_landscape_to_portrait(image):
    height, width = image.shape[:2]
    if height > 0 and (width / height) >= LANDSCAPE_ASPECT_LIMIT:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE), True
    return image, False


def _build_receipt_paper_mask(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    _h, s, v = cv2.split(hsv)

    bright = cv2.inRange(v, 130, 255)
    low_saturation = cv2.inRange(s, 0, 95)
    mask = cv2.bitwise_and(bright, low_saturation)

    kernel_close = np.ones((11, 11), np.uint8)
    kernel_open = np.ones((5, 5), np.uint8)

    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close, iterations=3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open, iterations=1)
    mask = cv2.dilate(mask, kernel_open, iterations=1)
    return mask


def _largest_receipt_paper_component(mask, image_shape):
    height, width = image_shape[:2]
    image_area = float(height * width)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    best_score = 0.0

    for contour in contours:
        area = float(cv2.contourArea(contour))
        if image_area <= 0:
            continue

        ratio = area / image_area
        if ratio < MIN_FOREGROUND_AREA_RATIO:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        if w < 120 or h < 180:
            continue

        aspect = max(w, h) / max(1, min(w, h))
        if aspect < 1.6:
            continue

        rect_area = float(w * h)
        fill = area / rect_area if rect_area else 0.0
        score = area * max(0.2, fill)

        if score > best_score:
            best = contour
            best_score = score

    return best


def _isolate_receipt_foreground(image):
    if cv2 is None or np is None:
        return image, False

    paper_mask = _build_receipt_paper_mask(image)
    contour = _largest_receipt_paper_component(paper_mask, image.shape)

    if contour is None:
        return image, False

    receipt_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.drawContours(receipt_mask, [contour], -1, 255, thickness=cv2.FILLED)
    receipt_mask = cv2.morphologyEx(
        receipt_mask,
        cv2.MORPH_CLOSE,
        np.ones((11, 11), np.uint8),
        iterations=2,
    )

    white = np.full_like(image, 255)
    isolated = np.where(receipt_mask[:, :, None] == 255, image, white)

    x, y, w, h = cv2.boundingRect(contour)
    pad = max(16, int(min(w, h) * 0.04))

    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(image.shape[1], x + w + pad)
    y1 = min(image.shape[0], y + h + pad)

    return isolated[y0:y1, x0:x1], True


def apply_receipt_image_preprocessing(file_bytes: bytes, filename: str) -> tuple[bytes, ReceiptImagePreprocessingDecision]:
    suffix = Path(filename or "").suffix.lower()
    if suffix and suffix not in IMAGE_SUFFIXES:
        return file_bytes, ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing",
            "original",
            [],
            ["unsupported_image_suffix"],
            None,
        )

    image = _decode_image(file_bytes)
    if image is None:
        return file_bytes, ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing",
            "original",
            [],
            ["image_decode_failed_or_cv2_unavailable"],
            None,
        )

    applied_steps: list[str] = []

    image, isolated = _isolate_receipt_foreground(image)
    if isolated:
        applied_steps.append("foreground_isolation")

    image, rotated = _rotate_landscape_to_portrait(image)
    if rotated:
        applied_steps.append("rotate_landscape_to_portrait")

    image, perspective_decision = normalize_receipt_perspective_image(image)
    if getattr(perspective_decision, "normalization_applied", False):
        applied_steps.append("perspective_normalization")

    output = _encode_image_png(image)
    if not output:
        return file_bytes, ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing",
            "original",
            applied_steps,
            ["output_encode_failed"],
            perspective_decision.to_dict(),
        )

    route = "original" if not applied_steps else "+".join(applied_steps)
    return output, ReceiptImagePreprocessingDecision(
        "receipt_image_preprocessing",
        route,
        applied_steps,
        [],
        perspective_decision.to_dict(),
    )
