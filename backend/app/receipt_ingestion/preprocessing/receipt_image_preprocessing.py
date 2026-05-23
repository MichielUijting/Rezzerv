from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    from rembg import remove as rembg_remove
except Exception:
    rembg_remove = None


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
LANDSCAPE_ASPECT_LIMIT = 1.20
MIN_DOCUMENT_AREA_RATIO = 0.04
ALPHA_THRESHOLD = 12


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


def _pil_rgb_to_bgr(image):
    if cv2 is None or np is None:
        return None
    rgb = image.convert("RGB")
    return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)


def _remove_background_with_rembg(file_bytes: bytes):
    """AI-background-removal before geometry/OCR.

    R9-21K:
    The previous OpenCV-only approach failed when receipt paper and background
    had similar brightness/saturation. `rembg` performs object segmentation
    first, after which OpenCV can crop/warp the receipt more reliably.
    """
    if rembg_remove is None:
        return None, "rembg_unavailable"
    if Image is None:
        return None, "pillow_unavailable"
    if cv2 is None or np is None:
        return None, "cv2_or_numpy_unavailable"

    try:
        rgba_bytes = rembg_remove(file_bytes)
        rgba = Image.open(BytesIO(rgba_bytes)).convert("RGBA")
    except Exception as exc:
        return None, f"rembg_failed:{type(exc).__name__}"

    alpha = np.array(rgba.getchannel("A"))
    ys, xs = np.where(alpha > ALPHA_THRESHOLD)

    if len(xs) == 0 or len(ys) == 0:
        return None, "rembg_empty_alpha_mask"

    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())

    width, height = rgba.size
    box_w = x1 - x0 + 1
    box_h = y1 - y0 + 1

    if box_w < 120 or box_h < 180:
        return None, "rembg_mask_too_small"

    pad = max(16, int(min(box_w, box_h) * 0.04))
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(width - 1, x1 + pad)
    y1 = min(height - 1, y1 + pad)

    # Composite segmented foreground on white so OCR sees a clean document image.
    white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    composed = Image.alpha_composite(white, rgba)
    cropped = composed.crop((x0, y0, x1 + 1, y1 + 1)).convert("RGB")

    bgr = _pil_rgb_to_bgr(cropped)
    if bgr is None:
        return None, "rembg_bgr_conversion_failed"

    return bgr, None


def _order_points(points):
    rect = np.zeros((4, 2), dtype="float32")
    s = points.sum(axis=1)
    rect[0] = points[np.argmin(s)]
    rect[2] = points[np.argmax(s)]
    diff = np.diff(points, axis=1)
    rect[1] = points[np.argmin(diff)]
    rect[3] = points[np.argmax(diff)]
    return rect


def _four_point_warp(image, points):
    rect = _order_points(points.astype("float32"))
    tl, tr, br, bl = rect

    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = int(max(width_a, width_b))

    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = int(max(height_a, height_b))

    if max_width < 160 or max_height < 260:
        return None

    dst = np.array(
        [
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ],
        dtype="float32",
    )

    matrix = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, matrix, (max_width, max_height), borderMode=cv2.BORDER_REPLICATE)

    if warped.shape[1] > warped.shape[0]:
        warped = cv2.rotate(warped, cv2.ROTATE_90_COUNTERCLOCKWISE)

    return warped


def _find_document_quadrilateral(image):
    height, width = image.shape[:2]
    image_area = float(height * width)

    ratio = height / 900.0 if height > 900 else 1.0
    small = cv2.resize(image, (int(width / ratio), int(height / ratio)))

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)

    edges = cv2.Canny(gray, 35, 110)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:30]

    best_quad = None
    best_score = 0.0

    for contour in contours:
        area_small = float(cv2.contourArea(contour))
        area = area_small * (ratio ** 2)
        if image_area <= 0 or (area / image_area) < MIN_DOCUMENT_AREA_RATIO:
            continue

        perimeter = cv2.arcLength(contour, True)
        for epsilon in (0.015, 0.02, 0.03, 0.04, 0.06, 0.08):
            approx = cv2.approxPolyDP(contour, epsilon * perimeter, True)
            if len(approx) != 4:
                continue

            quad = approx.reshape(4, 2).astype("float32") * ratio
            x, y, w, h = cv2.boundingRect(quad.astype("int32"))
            if w < 160 or h < 260:
                continue

            aspect = max(w, h) / max(1, min(w, h))
            if aspect < 1.45:
                continue

            rect_area = float(w * h)
            fill = area / rect_area if rect_area else 0.0
            score = area * max(0.2, min(fill, 1.0))

            if score > best_score:
                best_quad = quad
                best_score = score

    if best_quad is not None:
        return best_quad

    joined = cv2.dilate(edges, np.ones((23, 23), np.uint8), iterations=2)
    joined = cv2.morphologyEx(joined, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8), iterations=2)

    relaxed_contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    relaxed_contours = sorted(relaxed_contours, key=cv2.contourArea, reverse=True)[:10]

    best_box = None
    best_relaxed_score = 0.0

    for contour in relaxed_contours:
        area_small = float(cv2.contourArea(contour))
        area = area_small * (ratio ** 2)
        if image_area <= 0 or (area / image_area) < MIN_DOCUMENT_AREA_RATIO:
            continue

        rect = cv2.minAreaRect(contour)
        box_small = cv2.boxPoints(rect).astype("float32")
        box = box_small * ratio

        x, y, w, h = cv2.boundingRect(box.astype("int32"))
        if w < 160 or h < 260:
            continue

        aspect = max(w, h) / max(1, min(w, h))
        if aspect < 1.35:
            continue

        box_area = float(w * h)
        box_ratio = box_area / image_area if image_area else 0.0
        if box_ratio < 0.04 or box_ratio > 0.98:
            continue

        score = area * aspect
        if score > best_relaxed_score:
            best_box = box
            best_relaxed_score = score

    return best_box


def _remove_background_by_document_edges(image):
    if cv2 is None or np is None:
        return image, False

    quad = _find_document_quadrilateral(image)
    if quad is None:
        return image, False

    warped = _four_point_warp(image, quad)
    if warped is None:
        return image, False

    return warped, True


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

    applied_steps: list[str] = []
    fallback_reason: list[str] = []

    image, ai_reason = _remove_background_with_rembg(file_bytes)
    if image is not None:
        applied_steps.append("ai_background_removed")
    elif ai_reason:
        fallback_reason.append(ai_reason)

    if image is None:
        image = _decode_image(file_bytes)

    if image is None:
        return file_bytes, ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing",
            "original",
            [],
            fallback_reason + ["image_decode_failed_or_cv2_unavailable"],
            None,
        )

    image, document_extracted = _remove_background_by_document_edges(image)
    if document_extracted:
        applied_steps.append("document_edge_background_removed")

    output = _encode_image_png(image)
    if not output:
        return file_bytes, ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing",
            "original",
            applied_steps,
            fallback_reason + ["output_encode_failed"],
            None,
        )

    route = "original" if not applied_steps else "+".join(applied_steps)
    return output, ReceiptImagePreprocessingDecision(
        "receipt_image_preprocessing",
        route,
        applied_steps,
        fallback_reason,
        None,
    )
