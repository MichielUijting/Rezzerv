from ...services import receipt_service as _svc
from ...services.receipt_service import *

import os
import tempfile
from pathlib import Path

from .image.receipt_photo_normalizer import ReceiptPhotoNormalizer

# Feature flag
RECEIPT_PHOTO_NORMALIZATION_ENABLED = str(os.getenv("RECEIPT_PHOTO_NORMALIZATION_ENABLED", "true")).lower() in {"1","true","yes","on"}

_normalizer = ReceiptPhotoNormalizer()
_original_parse = _svc.parse_receipt_content


def parse_receipt_content(*args, **kwargs):
    if not RECEIPT_PHOTO_NORMALIZATION_ENABLED:
        return _original_parse(*args, **kwargs)

    try:
        image_path = kwargs.get("image_path") or kwargs.get("file_path")
        mime_type = kwargs.get("mime_type")

        if image_path:
            result = _normalizer.normalize(image_path, mime_type)
            if result.success and result.ocr_ready_path:
                kwargs["image_path"] = result.ocr_ready_path

        return _original_parse(*args, **kwargs)

    except Exception:
        return _original_parse(*args, **kwargs)

# monkey patch
_svc.parse_receipt_content = parse_receipt_content
