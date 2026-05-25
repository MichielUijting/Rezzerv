from pathlib import Path

p = Path("backend/app/receipt_ingestion/preprocessing/safe_rotation.py")
s = p.read_text(encoding="utf-8-sig")

backup = p.with_suffix(".py.bak")
backup.write_text(s, encoding="utf-8")

if "LANDSCAPE_ASPECT_LIMIT" not in s:
    s = s.replace(
        "MIN_CONFIDENCE = 0.55\n",
        "MIN_CONFIDENCE = 0.55\nLANDSCAPE_ASPECT_LIMIT = 1.20\n",
    )

if "def _is_landscape_image" not in s:
    s = s.replace(
        "\ndef apply_safe_rotation_preprocessing(file_bytes: bytes, filename: str)",
        """

def _is_landscape_image(image) -> bool:
    height, width = image.shape[:2]
    return height > 0 and (width / height) >= LANDSCAPE_ASPECT_LIMIT

def apply_safe_rotation_preprocessing(file_bytes: bytes, filename: str)"""
    )

marker = """    image = _decode(file_bytes)
    if image is None:
        return file_bytes, _fallback("image_decode_failed_or_cv2_unavailable")

"""

insert = """    image = _decode(file_bytes)
    if image is None:
        return file_bytes, _fallback("image_decode_failed_or_cv2_unavailable")

    if _is_landscape_image(image):
        rotated_bytes = _encode_png(cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE))
        if rotated_bytes:
            return rotated_bytes, SafeRotationDecision(
                "safe_rotation", True, "rotate_90_landscape", 90.0, 1.0, 1.0,
                0, None, [], [90.0]
            )

"""

if "rotate_90_landscape" not in s:
    if marker not in s:
        raise SystemExit("Patchpunt niet gevonden; niets aangepast.")
    s = s.replace(marker, insert, 1)

p.write_text(s, encoding="utf-8")

print("R9-20A patch toegepast")
