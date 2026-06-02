from pathlib import Path

root = Path("C:/Users/Gebruiker/Rezzerv_Github")

pipeline = root / "backend/app/receipt_ingestion/preprocessing/receipt_image_preprocessing.py"
pipeline.write_text(r'''from __future__ import annotations

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

def apply_receipt_image_preprocessing(file_bytes: bytes, filename: str) -> tuple[bytes, ReceiptImagePreprocessingDecision]:
    suffix = Path(filename or "").suffix.lower()
    if suffix and suffix not in IMAGE_SUFFIXES:
        return file_bytes, ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing", "original", [], ["unsupported_image_suffix"], None
        )

    image = _decode_image(file_bytes)
    if image is None:
        return file_bytes, ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing", "original", [], ["image_decode_failed_or_cv2_unavailable"], None
        )

    applied_steps: list[str] = []

    image, rotated = _rotate_landscape_to_portrait(image)
    if rotated:
        applied_steps.append("rotate_landscape_to_portrait")

    image, perspective_decision = normalize_receipt_perspective_image(image)
    if getattr(perspective_decision, "normalization_applied", False):
        applied_steps.append("perspective_normalization")

    output = _encode_image_png(image)
    if not output:
        return file_bytes, ReceiptImagePreprocessingDecision(
            "receipt_image_preprocessing", "original", applied_steps, ["output_encode_failed"], perspective_decision.to_dict()
        )

    route = "original" if not applied_steps else "+".join(applied_steps)
    return output, ReceiptImagePreprocessingDecision(
        "receipt_image_preprocessing", route, applied_steps, [], perspective_decision.to_dict()
    )
''', encoding="utf-8")

service = root / "backend/app/services/receipt_service.py"
s = service.read_text(encoding="utf-8-sig")

s = s.replace(
    "from app.receipt_ingestion.preprocessing.safe_rotation import apply_safe_rotation_preprocessing",
    "from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import apply_receipt_image_preprocessing",
)

s = s.replace(
    "ocr_file_bytes, safe_rotation_decision = apply_safe_rotation_preprocessing(file_bytes, filename)",
    "ocr_file_bytes, safe_rotation_decision = apply_receipt_image_preprocessing(file_bytes, filename)",
)

s = s.replace(
    "if safe_rotation_decision and safe_rotation_decision.selected_route == 'rotate_only':",
    "if safe_rotation_decision and safe_rotation_decision.selected_route != 'original':",
)

service.write_text(s, encoding="utf-8")

debug = root / "tools/R9-21A_export_receipt_preprocessing.py"
if debug.exists():
    d = debug.read_text(encoding="utf-8")
    if "apply_receipt_image_preprocessing" not in d:
        d = d.replace(
            "from PIL import Image, ImageOps\n",
            "from PIL import Image, ImageOps\nfrom app.receipt_ingestion.preprocessing.receipt_image_preprocessing import apply_receipt_image_preprocessing\n",
        )
        d = d.replace(
            "deskewed = _deskew_pil(rotated_90)\n    _save_pil(deskewed, case_dir / '03_deskewed.png')",
            "runtime_bytes, runtime_decision = apply_receipt_image_preprocessing(data, filename)\n    runtime_image = Image.open(io.BytesIO(runtime_bytes)).convert('RGB')\n    _save_pil(runtime_image, case_dir / '03_runtime_preprocessed.png')\n\n    deskewed = _deskew_pil(rotated_90)\n    _save_pil(deskewed, case_dir / '03_deskewed.png')",
        )
        d = d.replace(
            "output_dir={case_dir}\\n',",
            "output_dir={case_dir}\\nruntime_decision={runtime_decision.to_dict()}\\n',",
        )
        debug.write_text(d, encoding="utf-8")

print("R9-21C lokale patch toegepast.")
