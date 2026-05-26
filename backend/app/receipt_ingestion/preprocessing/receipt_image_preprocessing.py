from __future__ import annotations

from dataclasses import asdict, dataclass, field
from io import BytesIO
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

try:
    import numpy as np
except Exception:
    np = None

try:
    import cv2
except Exception:
    cv2 = None

try:
    from rembg import remove as rembg_remove
except Exception:
    rembg_remove = None


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
ALPHA_THRESHOLD = 12
MIN_MASK_COVERAGE = 0.01
MAX_MASK_COVERAGE = 0.98
MIN_CROP_WIDTH = 120
MIN_CROP_HEIGHT = 180


@dataclass
class ReceiptImagePreprocessingDecision:
    preprocessing_step: str
    selected_route: str
    applied_steps: list[str]
    fallback_reason: list[str]
    perspective_normalization: dict[str, Any] | None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _debug_dir() -> Path | None:
    value = os.environ.get("REZZERV_RECEIPT_PREPROCESS_DEBUG_DIR")
    if not value:
        return None
    path = Path(value)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_debug(name: str, image: Image.Image, diagnostics: dict[str, Any]) -> None:
    out = _debug_dir()
    if out is None:
        return
    path = out / name
    image.save(path)
    diagnostics.setdefault("debug_files", []).append(str(path))


def _encode_png(image: Image.Image) -> bytes:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _safe_original(file_bytes: bytes, reasons: list[str], diagnostics: dict[str, Any]) -> tuple[bytes, ReceiptImagePreprocessingDecision]:
    try:
        img = Image.open(BytesIO(file_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")
        diagnostics["original_size"] = [img.width, img.height]
        diagnostics["final_size"] = [img.width, img.height]
        _save_debug("00_input_original.png", img, diagnostics)
        _save_debug("40_final_runtime_preprocessed.png", img, diagnostics)
        return _encode_png(img), ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing",
            "original_safe_fallback",
            [],
            reasons,
            None,
            diagnostics,
        )
    except Exception as exc:
        reasons.append(f"fallback_decode_failed:{type(exc).__name__}")
        return file_bytes, ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing",
            "original_bytes_fallback",
            [],
            reasons,
            None,
            diagnostics,
        )




def _order_quad_points(points: Any) -> Any:
    pts = np.array(points, dtype="float32").reshape(4, 2)
    ordered = np.zeros((4, 2), dtype="float32")
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).reshape(4)
    ordered[0] = pts[np.argmin(sums)]
    ordered[2] = pts[np.argmax(sums)]
    ordered[1] = pts[np.argmin(diffs)]
    ordered[3] = pts[np.argmax(diffs)]
    return ordered




def _perspective_normalize_from_dark_receipt_region(rgba: Image.Image, diagnostics: dict[str, Any]) -> tuple[Image.Image | None, dict[str, Any] | None, str | None]:
    """Detect the receipt plane on the rembg white-composited image.

    R9-33F: alpha masks can describe the rembg segmentation/background rather than the actual
    receipt plane. For angled receipts, the stable signal is the dark/grey paper region on a
    white background. This routine therefore composes on white first, then finds the largest
    non-white receipt region and warps that quadrilateral.
    """
    if np is None:
        return None, None, "numpy_unavailable"
    if cv2 is None:
        return None, None, "cv2_unavailable"

    white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    composed = Image.alpha_composite(white, rgba).convert("RGB")
    _save_debug("18_dark_region_source_white_composite.png", composed, diagnostics)

    rgb = np.array(composed)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # Keep the actual receipt paper/text/shadow, reject the white rembg background.
    # High threshold is intentional: many receipt photos become light grey after rembg.
    mask = cv2.inRange(gray, 0, 246)

    # Connect the receipt surface into one contour while suppressing isolated OCR/text speckles.
    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (31, 31))
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open, iterations=1)
    diagnostics["dark_region_mask"] = {
        "threshold_gray_max": 246,
        "close_kernel": [31, 31],
        "open_kernel": [9, 9],
    }
    _save_debug("19_dark_receipt_region_mask.png", Image.fromarray(mask), diagnostics)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None, "no_dark_receipt_region_contours"

    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    image_area = float(mask.shape[0] * mask.shape[1]) if mask.size else 0.0
    coverage = area / image_area if image_area else 0.0

    if coverage < MIN_MASK_COVERAGE or coverage > MAX_MASK_COVERAGE:
        return None, {"contour_area": area, "coverage": coverage}, "dark_region_coverage_out_of_bounds"

    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
    method = "dark_region_approx_poly_dp"
    if len(approx) == 4:
        quad = approx.reshape(4, 2)
    else:
        rect = cv2.minAreaRect(contour)
        quad = cv2.boxPoints(rect)
        method = "dark_region_min_area_rect_fallback"

    ordered = _order_quad_points(quad)
    tl, tr, br, bl = ordered
    width_top = np.linalg.norm(tr - tl)
    width_bottom = np.linalg.norm(br - bl)
    height_right = np.linalg.norm(br - tr)
    height_left = np.linalg.norm(bl - tl)
    target_width = int(round(max(width_top, width_bottom)))
    target_height = int(round(max(height_right, height_left)))

    if target_width < MIN_CROP_WIDTH or target_height < MIN_CROP_HEIGHT:
        return None, {
            "method": method,
            "target_size": [target_width, target_height],
            "minimum_size": [MIN_CROP_WIDTH, MIN_CROP_HEIGHT],
        }, "dark_region_target_too_small"

    dst = np.array([
        [0, 0],
        [target_width - 1, 0],
        [target_width - 1, target_height - 1],
        [0, target_height - 1],
    ], dtype="float32")
    transform = cv2.getPerspectiveTransform(ordered.astype("float32"), dst)
    warped = cv2.warpPerspective(rgb, transform, (target_width, target_height), borderValue=(255, 255, 255))
    normalized = Image.fromarray(warped).convert("RGB")

    # Normalize orientation for OCR. Receipts should be portrait; rotate if the detected plane is landscape.
    orientation_applied = None
    if normalized.width > normalized.height:
        normalized = normalized.rotate(90, expand=True, fillcolor=(255, 255, 255))
        orientation_applied = "rotate_90_to_portrait"

    _save_debug("21_dark_region_perspective_normalized.png", normalized, diagnostics)
    detail = {
        "method": method,
        "contour_area": area,
        "coverage": coverage,
        "quad_points": [[float(x), float(y)] for x, y in ordered.tolist()],
        "target_size_before_orientation": [target_width, target_height],
        "final_size": [normalized.width, normalized.height],
        "orientation_applied": orientation_applied,
        "applied": True,
        "basis": "dark_receipt_region_on_rembg_white_composite",
    }
    diagnostics["dark_region_perspective_normalization"] = detail
    return normalized, detail, None

def _perspective_normalize_from_alpha(rgba: Image.Image, diagnostics: dict[str, Any]) -> tuple[Image.Image | None, dict[str, Any] | None, str | None]:
    if np is None:
        return None, None, "numpy_unavailable"
    if cv2 is None:
        return None, None, "cv2_unavailable"

    alpha = np.array(rgba.getchannel("A"))
    mask = (alpha > ALPHA_THRESHOLD).astype("uint8") * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None, "no_alpha_contours"

    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    image_area = float(mask.shape[0] * mask.shape[1]) if mask.size else 0.0
    coverage = area / image_area if image_area else 0.0
    if coverage < MIN_MASK_COVERAGE or coverage > MAX_MASK_COVERAGE:
        return None, {"contour_area": area, "coverage": coverage}, "contour_coverage_out_of_bounds"

    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
    method = "approx_poly_dp"
    if len(approx) == 4:
        quad = approx.reshape(4, 2)
    else:
        rect = cv2.minAreaRect(contour)
        quad = cv2.boxPoints(rect)
        method = "min_area_rect_fallback"

    ordered = _order_quad_points(quad)
    tl, tr, br, bl = ordered
    width_top = np.linalg.norm(tr - tl)
    width_bottom = np.linalg.norm(br - bl)
    height_right = np.linalg.norm(br - tr)
    height_left = np.linalg.norm(bl - tl)
    target_width = int(round(max(width_top, width_bottom)))
    target_height = int(round(max(height_right, height_left)))

    if target_width < MIN_CROP_WIDTH or target_height < MIN_CROP_HEIGHT:
        return None, {
            "method": method,
            "target_size": [target_width, target_height],
            "minimum_size": [MIN_CROP_WIDTH, MIN_CROP_HEIGHT],
        }, "perspective_target_too_small"

    # Keep receipt portrait-oriented for OCR: long side vertical.
    if target_width > target_height:
        target_width, target_height = target_height, target_width
        dst = np.array([
            [0, target_height - 1],
            [0, 0],
            [target_width - 1, 0],
            [target_width - 1, target_height - 1],
        ], dtype="float32")
    else:
        dst = np.array([
            [0, 0],
            [target_width - 1, 0],
            [target_width - 1, target_height - 1],
            [0, target_height - 1],
        ], dtype="float32")

    white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    composed = Image.alpha_composite(white, rgba).convert("RGB")
    source = np.array(composed)
    transform = cv2.getPerspectiveTransform(ordered.astype("float32"), dst)
    warped = cv2.warpPerspective(source, transform, (target_width, target_height), borderValue=(255, 255, 255))
    normalized = Image.fromarray(warped).convert("RGB")
    _save_debug("20_perspective_normalized.png", normalized, diagnostics)

    detail = {
        "method": method,
        "contour_area": area,
        "coverage": coverage,
        "quad_points": [[float(x), float(y)] for x, y in ordered.tolist()],
        "target_size": [target_width, target_height],
        "applied": True,
    }
    diagnostics["perspective_normalization"] = detail
    return normalized, detail, None

def _alpha_bbox_crop(rgba: Image.Image, diagnostics: dict[str, Any]) -> tuple[Image.Image | None, str | None]:
    if np is None:
        return None, "numpy_unavailable"

    alpha = np.array(rgba.getchannel("A"))
    ys, xs = np.where(alpha > ALPHA_THRESHOLD)

    total = int(alpha.shape[0] * alpha.shape[1])
    count = int(len(xs))
    coverage = float(count / total) if total else 0.0

    diagnostics["rembg_alpha"] = {
        "mask_pixels": count,
        "total_pixels": total,
        "coverage": coverage,
        "threshold": ALPHA_THRESHOLD,
    }
    _save_debug("10_rembg_alpha_mask.png", Image.fromarray(alpha), diagnostics)

    if count <= 0:
        return None, "rembg_empty_alpha_mask"
    if coverage < MIN_MASK_COVERAGE:
        return None, "rembg_mask_coverage_too_low"
    if coverage > MAX_MASK_COVERAGE:
        return None, "rembg_mask_coverage_too_high"

    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    width, height = rgba.size

    box_w = x1 - x0 + 1
    box_h = y1 - y0 + 1
    if box_w < MIN_CROP_WIDTH or box_h < MIN_CROP_HEIGHT:
        diagnostics["rembg_bbox_rejected"] = {
            "bbox_size": [box_w, box_h],
            "minimum_size": [MIN_CROP_WIDTH, MIN_CROP_HEIGHT],
        }
        return None, "rembg_bbox_too_small"

    pad = max(24, int(min(box_w, box_h) * 0.04))
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(width - 1, x1 + pad)
    y1 = min(height - 1, y1 + pad)

    white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    composed = Image.alpha_composite(white, rgba).convert("RGB")
    _save_debug("11_rembg_composited_full.png", composed, diagnostics)

    cropped = composed.crop((x0, y0, x1 + 1, y1 + 1)).convert("RGB")
    _save_debug("12_rembg_cropped.png", cropped, diagnostics)

    diagnostics["rembg_bbox"] = {
        "image_size": [width, height],
        "bbox": [x0, y0, x1, y1],
        "bbox_size": [cropped.width, cropped.height],
        "crop_reduces_image": cropped.width < width or cropped.height < height,
    }
    return cropped, None


def apply_receipt_image_preprocessing(file_bytes: bytes, filename: str) -> tuple[bytes, ReceiptImagePreprocessingDecision]:
    """R9-30A: generic rembg background neutralization.

    Runtime route:
    rembg -> white_composite -> dark_receipt_region_perspective_normalization -> alpha/pad crop fallback.

    Guardrails:
    - No status logic.
    - No OCR/parser branching by filename.
    - No PCA pilot filenames.
    - Generic contour/perspective normalization is allowed because OCR needs an upright receipt image.
    - Safe fallback preserves processing by returning the original image encoded as PNG where possible.
    """
    diagnostics: dict[str, Any] = {
        "filename": filename,
        "route_policy": "generic_no_filename_gate",
    }
    suffix = Path(filename or "").suffix.lower()

    if suffix and suffix not in IMAGE_SUFFIXES:
        return file_bytes, ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing",
            "original",
            [],
            ["unsupported_image_suffix"],
            None,
            diagnostics,
        )

    if rembg_remove is None:
        return _safe_original(file_bytes, ["rembg_unavailable"], diagnostics)

    try:
        original = Image.open(BytesIO(file_bytes))
        original = ImageOps.exif_transpose(original).convert("RGB")
        diagnostics["original_size"] = [original.width, original.height]
        _save_debug("00_input_original.png", original, diagnostics)
    except Exception as exc:
        return file_bytes, ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing",
            "original_bytes_fallback",
            [],
            [f"image_decode_failed:{type(exc).__name__}"],
            None,
            diagnostics,
        )

    try:
        rgba_bytes = rembg_remove(file_bytes)
        rgba = Image.open(BytesIO(rgba_bytes)).convert("RGBA")
        rgba = ImageOps.exif_transpose(rgba)
        diagnostics["rembg"] = {"available": True, "size": [rgba.width, rgba.height]}
        _save_debug("09_rembg_raw_rgba.png", rgba, diagnostics)
    except Exception as exc:
        return _safe_original(file_bytes, [f"rembg_failed:{type(exc).__name__}"], diagnostics)

    perspective_image, perspective_detail, perspective_reason = _perspective_normalize_from_dark_receipt_region(rgba, diagnostics)
    if perspective_image is not None:
        final_image = perspective_image
        selected_route = "R9-33F_rembg_dark_region_perspective_normalized"
        applied_steps = [
            "rembg_remove_background",
            "white_composite",
            "dark_receipt_region_detection",
            "perspective_normalization",
        ]
        fallback_reasons: list[str] = []
        perspective_payload = perspective_detail
    else:
        diagnostics["dark_region_perspective_normalization"] = {
            "applied": False,
            "reason": perspective_reason or "dark_region_perspective_normalization_failed",
            **(perspective_detail or {}),
        }
        alpha_image, alpha_detail, alpha_reason = _perspective_normalize_from_alpha(rgba, diagnostics)
        if alpha_image is not None:
            final_image = alpha_image
            selected_route = "R9-33E_rembg_alpha_perspective_normalized_fallback"
            applied_steps = ["rembg_remove_background", "white_composite", "alpha_contour_detection", "perspective_normalization"]
            fallback_reasons = [perspective_reason or "dark_region_perspective_not_applied"]
            perspective_payload = alpha_detail
        else:
            diagnostics["perspective_normalization"] = {
                "applied": False,
                "reason": alpha_reason or "alpha_perspective_normalization_failed",
                **(alpha_detail or {}),
            }
            cropped, reason = _alpha_bbox_crop(rgba, diagnostics)
            if cropped is None:
                return _safe_original(file_bytes, [reason or alpha_reason or perspective_reason or "rembg_crop_failed"], diagnostics)
            final_image = cropped
            selected_route = "R9-30A_generic_rembg_alpha_bbox_crop"
            applied_steps = ["rembg_remove_background", "white_composite", "alpha_bbox_crop"]
            fallback_reasons = [perspective_reason or alpha_reason or "perspective_normalization_not_applied"]
            perspective_payload = diagnostics.get("dark_region_perspective_normalization") or diagnostics.get("perspective_normalization")

    _save_debug("40_final_runtime_preprocessed.png", final_image, diagnostics)
    diagnostics["final_size"] = [final_image.width, final_image.height]

    return _encode_png(final_image), ReceiptImagePreprocessingDecision(
        "receipt_image_preprocessing",
        selected_route,
        applied_steps,
        fallback_reasons,
        perspective_payload,
        diagnostics,
    )



def warm_receipt_image_preprocessing() -> dict[str, Any]:
    """Warm the rembg runtime so the first user upload does not pay model initialization."""
    diagnostics: dict[str, Any] = {"warmup": "receipt_image_preprocessing"}
    if str(os.getenv("REZZERV_RECEIPT_STARTUP_REMBG_WARMUP", "false") or "false").strip().lower() not in {"1", "true", "yes", "on"}:
        diagnostics["status"] = "skipped"
        diagnostics["reason"] = "startup_rembg_warmup_disabled"
        return diagnostics
    if rembg_remove is None:
        diagnostics["status"] = "rembg_unavailable"
        return diagnostics
    try:
        sample = Image.new("RGB", (96, 160), (245, 245, 245))
        buffer = BytesIO()
        sample.save(buffer, format="PNG")
        _ = rembg_remove(buffer.getvalue())
        diagnostics["status"] = "ok"
    except Exception as exc:
        diagnostics["status"] = "failed"
        diagnostics["error"] = f"{type(exc).__name__}: {exc}"
    return diagnostics
