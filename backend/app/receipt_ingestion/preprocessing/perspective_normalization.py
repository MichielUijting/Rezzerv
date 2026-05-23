from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore


@dataclass
class PerspectiveNormalizationDecision:
    preprocessing_step: str
    normalization_applied: bool
    selected_route: str
    fallback_reason: list[str]
    contour_area_ratio: float
    output_width: int | None
    output_height: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _decision(applied: bool, route: str, reasons: list[str] | None = None, *, area_ratio: float = 0.0, width: int | None = None, height: int | None = None) -> PerspectiveNormalizationDecision:
    return PerspectiveNormalizationDecision(
        preprocessing_step='perspective_normalization',
        normalization_applied=applied,
        selected_route=route,
        fallback_reason=list(reasons or []),
        contour_area_ratio=round(float(area_ratio), 4),
        output_width=width,
        output_height=height,
    )


def _order_points(points):
    rect = np.zeros((4, 2), dtype='float32')
    s = points.sum(axis=1)
    rect[0] = points[np.argmin(s)]
    rect[2] = points[np.argmax(s)]
    diff = np.diff(points, axis=1)
    rect[1] = points[np.argmin(diff)]
    rect[3] = points[np.argmax(diff)]
    return rect


def _four_point_transform(image, points):
    rect = _order_points(points)
    tl, tr, br, bl = rect
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = int(max(width_a, width_b))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = int(max(height_a, height_b))
    if max_width < 80 or max_height < 120:
        return None
    dst = np.array([[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]], dtype='float32')
    matrix = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, matrix, (max_width, max_height))


def _find_document_contour(image):
    height, width = image.shape[:2]
    image_area = float(height * width)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
    for contour in candidates:
        area = float(cv2.contourArea(contour))
        ratio = area / image_area if image_area else 0.0
        if ratio < 0.08:
            continue
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.03 * peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype('float32'), ratio
    return None, 0.0


def normalize_receipt_perspective_image(image) -> tuple[Any, PerspectiveNormalizationDecision]:
    if cv2 is None or np is None:
        return image, _decision(False, 'original', ['cv2_or_numpy_unavailable'])
    if image is None:
        return image, _decision(False, 'original', ['image_missing'])
    points, area_ratio = _find_document_contour(image)
    if points is None:
        return image, _decision(False, 'original', ['document_contour_not_found'], area_ratio=area_ratio)
    warped = _four_point_transform(image, points)
    if warped is None:
        return image, _decision(False, 'original', ['perspective_warp_failed'], area_ratio=area_ratio)
    height, width = warped.shape[:2]
    if width > height:
        warped = cv2.rotate(warped, cv2.ROTATE_90_COUNTERCLOCKWISE)
        height, width = warped.shape[:2]
    return warped, _decision(True, 'document_contour_perspective_warp', [], area_ratio=area_ratio, width=width, height=height)
