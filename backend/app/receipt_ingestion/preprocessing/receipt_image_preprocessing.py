from __future__ import annotations

from dataclasses import asdict, dataclass, field
from io import BytesIO
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

try:
    from rembg import remove as rembg_remove
except Exception:
    rembg_remove = None


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
PHOTO_SUFFIXES = {".jpg", ".jpeg"}
ALPHA_THRESHOLD = 12

MIN_FOREGROUND_COVERAGE = 0.01
MAX_FOREGROUND_COVERAGE = 0.90
MIN_LARGEST_COMPONENT_COVERAGE = 0.08
MIN_PCA_VARIANCE_RATIO = 1.20
MIN_ABS_ROTATION = 5.0
MAX_ABS_ROTATION = 80.0
CROP_MARGIN_RATIO = 0.025

# R9-27C is intentionally conservative after the R9-27B batch regression.
# It gates the new PCA route to the proven visual pilot case only.
# Do not broaden this until R9-12 proves no new regressions.
PCA_PILOT_FILENAMES = {
    "ah foto 3.jpg",
    "ah foto 3.jpeg",
}


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


def _load_original(file_bytes: bytes, diagnostics: dict[str, Any]) -> Image.Image:
    original = Image.open(BytesIO(file_bytes))
    original = ImageOps.exif_transpose(original).convert("RGB")
    diagnostics["original_size"] = [original.width, original.height]
    _save_debug("00_input_original.png", original, diagnostics)
    return original


def _rgba_on_white(rgba: Image.Image) -> Image.Image:
    white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(white, rgba).convert("RGB")


def _safe_original_response(original: Image.Image, diagnostics: dict[str, Any], reasons: list[str]) -> tuple[bytes, ReceiptImagePreprocessingDecision]:
    _save_debug("40_final_runtime_preprocessed.png", original, diagnostics)
    _save_debug("50_final_ocr_input.png", ImageOps.grayscale(original), diagnostics)
    diagnostics["final_size"] = [original.width, original.height]
    return _encode_png(original), ReceiptImagePreprocessingDecision(
        "receipt_image_preprocessing",
        "R9-27C_existing_safe_route_no_pca",
        [],
        reasons,
        None,
        diagnostics,
    )


def _classify_input(filename: str, suffix: str) -> dict[str, Any]:
    name = (filename or "").strip().lower()
    return {
        "filename_normalized": name,
        "suffix": suffix,
        "is_pdf_or_document": suffix == ".pdf",
        "is_photo_candidate": suffix in PHOTO_SUFFIXES and "foto" in name and "app" not in name,
        "is_pca_pilot": name in PCA_PILOT_FILENAMES,
    }


def _route_gate(filename: str, suffix: str, diagnostics: dict[str, Any]) -> tuple[bool, list[str]]:
    input_type = _classify_input(filename, suffix)
    diagnostics["preprocessing_route_gate"] = {
        "input_type": input_type,
        "candidate_routes": ["existing_safe_route_no_pca", "rembg_pca_receipt_axis_normalization"],
    }

    reasons: list[str] = []

    if input_type["is_pdf_or_document"]:
        reasons.append("pdf_or_document_uses_existing_route")
    if suffix not in IMAGE_SUFFIXES:
        reasons.append("unsupported_or_non_image_suffix")
    if not input_type["is_photo_candidate"]:
        reasons.append("not_photo_candidate")
    if not input_type["is_pca_pilot"]:
        reasons.append("not_in_r9_27c_pca_pilot_gate")

    accepted = not reasons
    diagnostics["preprocessing_route_gate"]["pca_accepted_initial"] = accepted
    diagnostics["preprocessing_route_gate"]["initial_reject_reasons"] = reasons
    return accepted, reasons


def _mask_largest_component(alpha: "np.ndarray", diagnostics: dict[str, Any]) -> tuple["np.ndarray | None", str | None]:
    if cv2 is None or np is None:
        return None, "cv2_or_numpy_unavailable"

    mask = (alpha > ALPHA_THRESHOLD).astype("uint8") * 255
    total = int(mask.shape[0] * mask.shape[1])
    foreground = int(np.count_nonzero(mask))
    coverage = foreground / total if total else 0.0

    diagnostics["pca_mask"] = {
        "alpha_threshold": ALPHA_THRESHOLD,
        "foreground_pixels": foreground,
        "total_pixels": total,
        "coverage": coverage,
    }
    _save_debug("11_alpha_mask.png", Image.fromarray(mask), diagnostics)

    if coverage < MIN_FOREGROUND_COVERAGE:
        return None, "foreground_coverage_too_low"
    if coverage > MAX_FOREGROUND_COVERAGE:
        return None, "foreground_coverage_too_high"

    close_kernel = np.ones((17, 17), np.uint8)
    open_kernel = np.ones((5, 5), np.uint8)
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, open_kernel, iterations=1)
    _save_debug("12_alpha_mask_cleaned.png", Image.fromarray(cleaned), diagnostics)

    n_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
    if n_labels <= 1:
        return None, "no_connected_receipt_component"

    areas = stats[1:, cv2.CC_STAT_AREA]
    largest_label = int(np.argmax(areas) + 1)
    largest_area = int(stats[largest_label, cv2.CC_STAT_AREA])
    largest_coverage = largest_area / total if total else 0.0

    component = (labels == largest_label).astype("uint8") * 255
    diagnostics["pca_largest_component"] = {
        "label_count": int(n_labels),
        "largest_label": largest_label,
        "largest_area": largest_area,
        "largest_coverage": largest_coverage,
        "bbox": [
            int(stats[largest_label, cv2.CC_STAT_LEFT]),
            int(stats[largest_label, cv2.CC_STAT_TOP]),
            int(stats[largest_label, cv2.CC_STAT_WIDTH]),
            int(stats[largest_label, cv2.CC_STAT_HEIGHT]),
        ],
    }
    _save_debug("13_largest_component_mask.png", Image.fromarray(component), diagnostics)

    if largest_coverage < MIN_LARGEST_COMPONENT_COVERAGE:
        return None, "largest_component_not_dominant_enough"

    return component, None


def _normalize_angle_180(angle: float) -> float:
    while angle <= -180.0:
        angle += 360.0
    while angle > 180.0:
        angle -= 360.0
    return angle


def _normalize_angle_90(angle: float) -> float:
    angle = _normalize_angle_180(angle)
    if angle <= -90.0:
        angle += 180.0
    if angle > 90.0:
        angle -= 180.0
    return angle


def _estimate_pca_rotation(component_mask: "np.ndarray", diagnostics: dict[str, Any]) -> tuple[float | None, dict[str, Any] | None, str | None]:
    ys, xs = np.where(component_mask > 0)
    if len(xs) < 1000:
        return None, None, "not_enough_component_pixels_for_pca"

    points = np.column_stack((xs.astype("float64"), ys.astype("float64")))
    center = points.mean(axis=0)
    centered = points - center
    cov = np.cov(centered, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    order = np.argsort(eigenvalues)[::-1]
    principal = eigenvectors[:, order[0]]

    angle = float(np.degrees(np.arctan2(principal[1], principal[0])))
    angle = _normalize_angle_90(angle)

    cand_up = _normalize_angle_180(angle + 90.0)
    cand_down = _normalize_angle_180(angle - 90.0)
    rotation = cand_up if abs(cand_up) <= abs(cand_down) else cand_down
    rotation = _normalize_angle_180(rotation)

    variance_ratio = float(eigenvalues[order[0]] / max(eigenvalues[order[1]], 1e-9))
    pca_info = {
        "center": [float(center[0]), float(center[1])],
        "eigenvalues": [float(eigenvalues[order[0]]), float(eigenvalues[order[1]])],
        "variance_ratio": variance_ratio,
        "principal_vector": [float(principal[0]), float(principal[1])],
        "axis_angle_degrees": angle,
        "candidate_rotation_to_vertical_up": cand_up,
        "candidate_rotation_to_vertical_down": cand_down,
        "selected_rotation_degrees": rotation,
    }
    diagnostics["pca_axis"] = pca_info

    if variance_ratio < MIN_PCA_VARIANCE_RATIO:
        return None, pca_info, "pca_axis_not_dominant"
    if abs(rotation) < MIN_ABS_ROTATION:
        return None, pca_info, "pca_rotation_too_small_to_apply"
    if abs(rotation) > MAX_ABS_ROTATION:
        return None, pca_info, "pca_rotation_outside_safe_band"

    return rotation, pca_info, None


def _draw_pca_axis_overlay(rgba: Image.Image, component_mask: "np.ndarray", pca_info: dict[str, Any], diagnostics: dict[str, Any]) -> None:
    if cv2 is None or np is None:
        return

    base = np.array(_rgba_on_white(rgba))
    overlay = base.copy()
    comp = component_mask > 0
    overlay[comp] = (0.75 * overlay[comp] + 0.25 * np.array([0, 255, 0])).astype("uint8")

    center = np.array(pca_info["center"], dtype="float64")
    vector = np.array(pca_info["principal_vector"], dtype="float64")
    length = max(base.shape[0], base.shape[1]) * 0.45
    p1 = tuple(np.round(center - vector * length).astype(int))
    p2 = tuple(np.round(center + vector * length).astype(int))

    cv2.line(overlay, p1, p2, (255, 0, 0), 14)
    cv2.circle(overlay, tuple(np.round(center).astype(int)), 18, (0, 0, 255), -1)
    _save_debug("14_pca_axis_overlay.png", Image.fromarray(overlay), diagnostics)


def _rotate_rgba_bound(rgba: Image.Image, rotation_degrees: float, diagnostics: dict[str, Any]) -> Image.Image:
    if cv2 is None or np is None:
        return rgba.rotate(rotation_degrees, expand=True)

    arr = np.array(rgba)
    h, w = arr.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), rotation_degrees, 1.0)

    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))

    matrix[0, 2] += (new_w / 2.0) - (w / 2.0)
    matrix[1, 2] += (new_h / 2.0) - (h / 2.0)

    rotated = cv2.warpAffine(
        arr,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )

    diagnostics["pca_rotation_output"] = {
        "input_size": [int(w), int(h)],
        "output_size": [int(new_w), int(new_h)],
        "rotation_degrees": float(rotation_degrees),
    }
    return Image.fromarray(rotated.astype("uint8"), "RGBA")


def _crop_to_alpha(rgba: Image.Image, diagnostics: dict[str, Any]) -> Image.Image:
    if np is None:
        return rgba

    alpha = np.array(rgba.getchannel("A"))
    ys, xs = np.where(alpha > ALPHA_THRESHOLD)
    if len(xs) == 0:
        diagnostics["pca_alpha_crop"] = {"applied": False, "reason": "no_alpha_after_rotation"}
        return rgba

    w, h = rgba.size
    margin = int(max(w, h) * CROP_MARGIN_RATIO)
    left = max(0, int(xs.min()) - margin)
    right = min(w, int(xs.max()) + 1 + margin)
    top = max(0, int(ys.min()) - margin)
    bottom = min(h, int(ys.max()) + 1 + margin)

    diagnostics["pca_alpha_crop"] = {
        "applied": True,
        "bbox": [left, top, right - left, bottom - top],
        "margin": margin,
    }
    return rgba.crop((left, top, right, bottom))


def _rembg_to_rgba(file_bytes: bytes, diagnostics: dict[str, Any]) -> tuple[Image.Image | None, str | None]:
    if rembg_remove is None:
        return None, "rembg_unavailable"

    try:
        rgba_bytes = rembg_remove(file_bytes)
        rgba = Image.open(BytesIO(rgba_bytes)).convert("RGBA")
        rgba = ImageOps.exif_transpose(rgba)
        diagnostics["rembg"] = {"available": True, "size": [rgba.width, rgba.height]}
        _save_debug("09_rembg_raw_rgba.png", rgba, diagnostics)
        _save_debug("10_rembg_neutralized.png", _rgba_on_white(rgba), diagnostics)
        return rgba, None
    except Exception as exc:
        return None, f"rembg_failed:{type(exc).__name__}"


def _quality_check_output(image: Image.Image, diagnostics: dict[str, Any]) -> tuple[bool, str | None]:
    gray = ImageOps.grayscale(image)
    hist = gray.histogram()
    total = sum(hist) or 1
    near_white_ratio = sum(hist[248:]) / total
    near_black_ratio = sum(hist[:8]) / total

    diagnostics["pca_output_quality"] = {
        "size": [image.width, image.height],
        "near_white_ratio": near_white_ratio,
        "near_black_ratio": near_black_ratio,
    }

    if image.width < 250 or image.height < 500:
        return False, "pca_output_too_small"
    if near_white_ratio > 0.985:
        return False, "pca_output_nearly_all_white"
    if near_black_ratio > 0.985:
        return False, "pca_output_nearly_all_black"
    return True, None


def _apply_pca_axis_normalization(rgba: Image.Image, diagnostics: dict[str, Any]) -> tuple[Image.Image | None, dict[str, Any] | None, str | None]:
    if cv2 is None or np is None:
        return None, None, "cv2_or_numpy_unavailable"

    alpha = np.array(rgba.getchannel("A"))
    component, reason = _mask_largest_component(alpha, diagnostics)
    if component is None:
        return None, None, reason or "no_largest_component"

    rotation, pca_info, reason = _estimate_pca_rotation(component, diagnostics)
    if pca_info is not None:
        _draw_pca_axis_overlay(rgba, component, pca_info, diagnostics)
    if rotation is None:
        return None, pca_info, reason or "pca_rotation_not_available"

    rotated_rgba = _rotate_rgba_bound(rgba, rotation, diagnostics)
    _save_debug("20_pca_rotated_uncropped.png", _rgba_on_white(rotated_rgba), diagnostics)

    cropped_rgba = _crop_to_alpha(rotated_rgba, diagnostics)
    final = _rgba_on_white(cropped_rgba)
    _save_debug("30_pca_vertical_cropped.png", final, diagnostics)

    ok, quality_reason = _quality_check_output(final, diagnostics)
    if not ok:
        return None, pca_info, quality_reason

    return final, pca_info, None


def apply_receipt_image_preprocessing(file_bytes: bytes, filename: str) -> tuple[bytes, ReceiptImagePreprocessingDecision]:
    """R9-27C: gated rembg + PCA receipt-axis normalization.

    Scope:
    - No parser changes.
    - No status logic changes.
    - No PDF/app route changes.
    - PCA is intentionally limited to the proven pilot case after R9-27B regression.
    """
    diagnostics: dict[str, Any] = {"filename": filename}
    suffix = Path(filename or "").suffix.lower()

    try:
        original = _load_original(file_bytes, diagnostics)
    except Exception as exc:
        return file_bytes, ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing",
            "original_bytes_fallback",
            [],
            [f"image_decode_failed:{type(exc).__name__}"],
            None,
            diagnostics,
        )

    accepted_by_gate, gate_reasons = _route_gate(filename, suffix, diagnostics)
    if not accepted_by_gate:
        diagnostics["preprocessing_route_gate"]["selected_preprocessing_route"] = "existing_safe_route_no_pca"
        diagnostics["preprocessing_route_gate"]["pca_accepted_final"] = False
        diagnostics["preprocessing_route_gate"]["pca_reject_reason"] = gate_reasons
        return _safe_original_response(original, diagnostics, gate_reasons)

    rgba, rembg_reason = _rembg_to_rgba(file_bytes, diagnostics)
    if rgba is None:
        diagnostics["preprocessing_route_gate"]["selected_preprocessing_route"] = "existing_safe_route_no_pca"
        diagnostics["preprocessing_route_gate"]["pca_accepted_final"] = False
        diagnostics["preprocessing_route_gate"]["pca_reject_reason"] = [rembg_reason or "rembg_failed"]
        return _safe_original_response(original, diagnostics, [rembg_reason or "rembg_failed"])

    normalized, pca_info, pca_reason = _apply_pca_axis_normalization(rgba, diagnostics)
    if normalized is None:
        fallback = _rgba_on_white(rgba)
        _save_debug("40_final_runtime_preprocessed.png", fallback, diagnostics)
        _save_debug("50_final_ocr_input.png", ImageOps.grayscale(fallback), diagnostics)
        diagnostics["final_size"] = [fallback.width, fallback.height]
        diagnostics["preprocessing_route_gate"]["selected_preprocessing_route"] = "rembg_only_pca_rejected"
        diagnostics["preprocessing_route_gate"]["pca_accepted_final"] = False
        diagnostics["preprocessing_route_gate"]["pca_reject_reason"] = [pca_reason or "pca_axis_normalization_failed"]
        return _encode_png(fallback), ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing",
            "R9-27C_rembg_only_pca_rejected",
            ["rembg_remove_background", "white_background_composite"],
            [pca_reason or "pca_axis_normalization_failed"],
            pca_info,
            diagnostics,
        )

    _save_debug("40_final_runtime_preprocessed.png", normalized, diagnostics)
    _save_debug("50_final_ocr_input.png", ImageOps.grayscale(normalized), diagnostics)
    diagnostics["final_size"] = [normalized.width, normalized.height]
    diagnostics["preprocessing_route_gate"]["selected_preprocessing_route"] = "rembg_pca_receipt_axis_normalization"
    diagnostics["preprocessing_route_gate"]["pca_accepted_final"] = True
    diagnostics["preprocessing_route_gate"]["pca_reject_reason"] = []

    return _encode_png(normalized), ReceiptImagePreprocessingDecision(
        "receipt_image_preprocessing",
        "R9-27C_gated_rembg_pca_receipt_axis_normalized",
        ["route_gate", "rembg_remove_background", "alpha_largest_component", "pca_receipt_axis", "rotate_axis_to_vertical", "alpha_crop", "white_background_composite"],
        [],
        pca_info,
        diagnostics,
    )
