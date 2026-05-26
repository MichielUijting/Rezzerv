$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-33F apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path

path = Path('backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py')
text = path.read_text(encoding='utf-8')

helper_anchor = 'def _perspective_normalize_from_alpha(rgba: Image.Image, diagnostics: dict[str, Any]) -> tuple[Image.Image | None, dict[str, Any] | None, str | None]:\n'
helper_block = r'''

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
'''
if '_perspective_normalize_from_dark_receipt_region(' not in text:
    if helper_anchor not in text:
        raise SystemExit('R9-33F helper anchor not found')
    text = text.replace(helper_anchor, helper_block + '\n' + helper_anchor, 1)

old = '''    perspective_image, perspective_detail, perspective_reason = _perspective_normalize_from_alpha(rgba, diagnostics)
    if perspective_image is not None:
        final_image = perspective_image
        selected_route = "R9-33E_rembg_perspective_normalized"
        applied_steps = ["rembg_remove_background", "white_composite", "alpha_contour_detection", "perspective_normalization"]
        fallback_reasons: list[str] = []
        perspective_payload = perspective_detail
    else:
        diagnostics["perspective_normalization"] = {
            "applied": False,
            "reason": perspective_reason or "perspective_normalization_failed",
            **(perspective_detail or {}),
        }
        cropped, reason = _alpha_bbox_crop(rgba, diagnostics)
        if cropped is None:
            return _safe_original(file_bytes, [reason or perspective_reason or "rembg_crop_failed"], diagnostics)
        final_image = cropped
        selected_route = "R9-30A_generic_rembg_alpha_bbox_crop"
        applied_steps = ["rembg_remove_background", "white_composite", "alpha_bbox_crop"]
        fallback_reasons = [perspective_reason or "perspective_normalization_not_applied"]
        perspective_payload = diagnostics.get("perspective_normalization")
'''
new = '''    perspective_image, perspective_detail, perspective_reason = _perspective_normalize_from_dark_receipt_region(rgba, diagnostics)
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
'''
if old not in text:
    raise SystemExit('R9-33F flow anchor not found')
text = text.replace(old, new, 1)

text = text.replace(
    'rembg -> white_composite -> perspective_normalization -> alpha_bbox_crop fallback.',
    'rembg -> white_composite -> dark_receipt_region_perspective_normalization -> alpha/pad crop fallback.',
    1,
)

compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('R9-33F applied: perspective is based on dark receipt region after rembg white composite')
'@

$py | python -
if ($LASTEXITCODE -ne 0) {
  Write-Error "R9-33F failed: Python patch failed"
  exit 1
}

git --no-pager diff -- backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py

git add backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py
git commit -m 'R9-33F use dark receipt region for perspective normalization'
git push

Write-Host 'R9-33F toegepast en gepusht.'
