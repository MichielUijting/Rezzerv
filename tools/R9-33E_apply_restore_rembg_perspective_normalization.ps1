$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-33E apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path

path = Path('backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py')
text = path.read_text(encoding='utf-8')

if 'try:\n    import cv2\nexcept Exception:\n    cv2 = None\n' not in text:
    anchor = "try:\n    import numpy as np\nexcept Exception:\n    np = None\n\n"
    if anchor not in text:
        raise SystemExit('R9-33E import anchor not found')
    text = text.replace(anchor, anchor + "try:\n    import cv2\nexcept Exception:\n    cv2 = None\n\n", 1)

helper_anchor = 'def _alpha_bbox_crop(rgba: Image.Image, diagnostics: dict[str, Any]) -> tuple[Image.Image | None, str | None]:\n'
helper_block = r'''

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
'''
if '_perspective_normalize_from_alpha(' not in text:
    if helper_anchor not in text:
        raise SystemExit('R9-33E helper anchor not found')
    text = text.replace(helper_anchor, helper_block + '\n' + helper_anchor, 1)

old_doc = '''    Runtime route:
    rembg -> white_composite -> alpha_bbox_crop.

    Guardrails:
    - No status logic.
    - No OCR/parser branching by filename.
    - No PCA pilot filenames.
    - No contour forcing, perspective normalization, deskew, or edge-join reconstruction.
    - Safe fallback preserves processing by returning the original image encoded as PNG where possible.
'''
new_doc = '''    Runtime route:
    rembg -> white_composite -> perspective_normalization -> alpha_bbox_crop fallback.

    Guardrails:
    - No status logic.
    - No OCR/parser branching by filename.
    - No PCA pilot filenames.
    - Generic contour/perspective normalization is allowed because OCR needs an upright receipt image.
    - Safe fallback preserves processing by returning the original image encoded as PNG where possible.
'''
if old_doc in text:
    text = text.replace(old_doc, new_doc, 1)

old_flow = '''    cropped, reason = _alpha_bbox_crop(rgba, diagnostics)
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
'''
new_flow = '''    perspective_image, perspective_detail, perspective_reason = _perspective_normalize_from_alpha(rgba, diagnostics)
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
'''
if old_flow not in text:
    raise SystemExit('R9-33E flow anchor not found')
text = text.replace(old_flow, new_flow, 1)

compile(text, str(path), 'exec')
path.write_text(text, encoding='utf-8')
print('R9-33E applied: rembg perspective normalization restored before OCR')
'@

$py | python -
if ($LASTEXITCODE -ne 0) {
  Write-Error "R9-33E failed: Python patch failed"
  exit 1
}

git --no-pager diff -- backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py

git add backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py
git commit -m 'R9-33E restore rembg perspective normalization before OCR'
git push

Write-Host 'R9-33E toegepast en gepusht.'
