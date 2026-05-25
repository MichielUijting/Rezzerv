from pathlib import Path

root = Path(r"C:\Users\Gebruiker\Rezzerv_Github")
p = root / "backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py"
s = p.read_text(encoding="utf-8")

if "R9-25B_rembg_alpha_geometry_normalized" not in s:
    raise SystemExit("R9-25C stop: verwachte R9-25B basis niet gevonden.")

insert_after = """def _composite_rgba_on_white(rgba_arr) -> Image.Image:
    rgba = Image.fromarray(rgba_arr.astype("uint8"), "RGBA")
    white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(white, rgba).convert("RGB")


"""

addition = """def _rotate_to_vertical_from_alpha(rgba_arr, diagnostics: dict[str, Any]):
    alpha = rgba_arr[:, :, 3]
    mask = (alpha > ALPHA_THRESHOLD).astype("uint8") * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        diagnostics["vertical_rotation"] = {"applied": False, "reason": "no_alpha_contour_after_warp"}
        return rgba_arr

    contour = max(contours, key=cv2.contourArea)
    rect = cv2.minAreaRect(contour)
    (_cx, _cy), (rw, rh), angle = rect

    if rw >= rh:
        long_axis_angle = angle
    else:
        long_axis_angle = angle + 90.0

    rotation = 90.0 - float(long_axis_angle)
    while rotation <= -90:
        rotation += 180
    while rotation > 90:
        rotation -= 180

    diagnostics["vertical_rotation"] = {
        "rect_size": [float(rw), float(rh)],
        "min_area_angle": float(angle),
        "long_axis_angle": float(long_axis_angle),
        "rotation_degrees": float(rotation),
    }

    if abs(rotation) < 1.0:
        diagnostics["vertical_rotation"]["applied"] = False
        diagnostics["vertical_rotation"]["reason"] = "already_vertical"
        return rgba_arr

    h, w = rgba_arr.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), rotation, 1.0)

    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))

    matrix[0, 2] += (new_w / 2.0) - (w / 2.0)
    matrix[1, 2] += (new_h / 2.0) - (h / 2.0)

    rotated = cv2.warpAffine(
        rgba_arr,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )

    diagnostics["vertical_rotation"]["applied"] = True
    diagnostics["vertical_rotation"]["output_size"] = [int(new_w), int(new_h)]
    return rotated


"""

if addition not in s:
    s = s.replace(insert_after, insert_after + addition)

old = """    warped_preview = _composite_rgba_on_white(warped_rgba)
    _save_debug("30_perspective_warp.png", warped_preview, diagnostics)

    w, h = warped_preview.size
"""

new = """    warped_preview = _composite_rgba_on_white(warped_rgba)
    _save_debug("30_perspective_warp.png", warped_preview, diagnostics)

    warped_rgba = _rotate_to_vertical_from_alpha(warped_rgba, diagnostics)
    warped_preview = _composite_rgba_on_white(warped_rgba)
    _save_debug("35_alpha_axis_vertical_rotated.png", warped_preview, diagnostics)

    w, h = warped_preview.size
"""

if old not in s:
    raise SystemExit("R9-25C stop: rotatiepatchpunt niet gevonden.")

s = s.replace(old, new, 1)
s = s.replace('"R9-25B_rembg_alpha_geometry_normalized"', '"R9-25C_rembg_alpha_axis_vertical_normalized"')
s = s.replace(
    '["rembg_remove_background", "alpha_mask_largest_contour", "alpha_quad_detection", "rgba_perspective_warp", "white_background_composite"]',
    '["rembg_remove_background", "alpha_mask_largest_contour", "alpha_quad_detection", "rgba_perspective_warp", "alpha_axis_vertical_rotation", "white_background_composite"]',
)

p.write_text(s, encoding="utf-8")
print("R9-25C toegepast: verticale rotatie op basis van alpha-long-axis toegevoegd.")
