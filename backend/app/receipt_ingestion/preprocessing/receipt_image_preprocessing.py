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
    rembg -> white_composite -> alpha_bbox_crop.

    Guardrails:
    - No status logic.
    - No OCR/parser branching by filename.
    - No PCA pilot filenames.
    - No contour forcing, perspective normalization, deskew, or edge-join reconstruction.
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

    cropped, reason = _alpha_bbox_crop(rgba, diagnostics)
    if cropped is None:
        return _safe_original(file_bytes, [reason or "rembg_crop_failed"], diagnostics)

    _save_debug("40_final_runtime_preprocessed.png", cropped, diagnostics)
    diagnostics["final_size"] = [cropped.width, cropped.height]

    return _encode_png(cropped), ReceiptImagePreprocessingDecision(
        "receipt_image_preprocessing",
        "R9-30A_generic_rembg_alpha_bbox_crop",
        ["rembg_remove_background", "white_composite", "alpha_bbox_crop"],
        [],
        None,
        diagnostics,
    )
