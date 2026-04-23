from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from app.domains.receipts.image.receipt_photo_normalizer import ReceiptPhotoNormalizer

from . import receipt_service as _receipt_service

LOGGER = logging.getLogger(__name__)
RECEIPT_PHOTO_NORMALIZATION_ENABLED = True
_PHOTO_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png"}
_NORMALIZER = ReceiptPhotoNormalizer()
_ORIGINAL_PARSE_RECEIPT_CONTENT = _receipt_service.parse_receipt_content


def _looks_like_photo_mime(mime_type: Any) -> bool:
    return str(mime_type or "").strip().lower() in _PHOTO_MIME_TYPES


def _normalize_photo_bytes(filename: str, mime_type: str, file_bytes: bytes) -> tuple[str, str, bytes] | None:
    suffix = Path(filename or "receipt").suffix or ".jpg"
    with tempfile.TemporaryDirectory(prefix="rezzerv_receipt_photo_") as temp_dir:
        input_path = Path(temp_dir) / f"input{suffix}"
        input_path.write_bytes(file_bytes)
        result = _NORMALIZER.normalize(str(input_path), mime_type)
        LOGGER.info(
            "receipt_photo_normalization success=%s used_fallback=%s confidence=%.3f reason=%s detected_as_photo=%s original_path=%s normalized_path=%s ocr_ready_path=%s",
            result.success,
            result.used_fallback,
            float(result.confidence or 0.0),
            result.reason,
            result.detected_as_photo,
            result.original_path,
            result.normalized_path,
            result.ocr_ready_path,
        )
        if result.success and result.ocr_ready_path:
            normalized_bytes = Path(result.ocr_ready_path).read_bytes()
            return Path(filename or "receipt.png").with_suffix(".png").name, "image/png", normalized_bytes
        return None


def parse_receipt_content(*args, **kwargs):
    if not RECEIPT_PHOTO_NORMALIZATION_ENABLED:
        return _ORIGINAL_PARSE_RECEIPT_CONTENT(*args, **kwargs)

    mutable_args = list(args)
    try:
        if len(mutable_args) >= 3 and isinstance(mutable_args[0], str) and isinstance(mutable_args[2], (bytes, bytearray)):
            filename = mutable_args[0]
            mime_type = str(mutable_args[1] or "")
            file_bytes = bytes(mutable_args[2])
            if _looks_like_photo_mime(mime_type):
                normalized = _normalize_photo_bytes(filename, mime_type, file_bytes)
                if normalized:
                    new_filename, new_mime_type, new_bytes = normalized
                    mutable_args[0] = new_filename
                    mutable_args[1] = new_mime_type
                    mutable_args[2] = new_bytes
        elif isinstance(kwargs.get("file_bytes"), (bytes, bytearray)) and _looks_like_photo_mime(kwargs.get("mime_type")):
            normalized = _normalize_photo_bytes(
                str(kwargs.get("filename") or kwargs.get("original_filename") or "receipt.png"),
                str(kwargs.get("mime_type") or ""),
                bytes(kwargs.get("file_bytes") or b""),
            )
            if normalized:
                new_filename, new_mime_type, new_bytes = normalized
                kwargs["filename"] = new_filename
                kwargs["mime_type"] = new_mime_type
                kwargs["file_bytes"] = new_bytes
        elif kwargs.get("image_path") and _looks_like_photo_mime(kwargs.get("mime_type")):
            result = _NORMALIZER.normalize(str(kwargs.get("image_path")), str(kwargs.get("mime_type") or ""))
            LOGGER.info(
                "receipt_photo_normalization success=%s used_fallback=%s confidence=%.3f reason=%s detected_as_photo=%s original_path=%s normalized_path=%s ocr_ready_path=%s",
                result.success,
                result.used_fallback,
                float(result.confidence or 0.0),
                result.reason,
                result.detected_as_photo,
                result.original_path,
                result.normalized_path,
                result.ocr_ready_path,
            )
            if result.success and result.ocr_ready_path:
                kwargs["image_path"] = result.ocr_ready_path
    except Exception as exc:
        LOGGER.warning("receipt_photo_normalization_failed error=%s", exc)

    return _ORIGINAL_PARSE_RECEIPT_CONTENT(*tuple(mutable_args), **kwargs)


_receipt_service.parse_receipt_content = parse_receipt_content
