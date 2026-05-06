from __future__ import annotations

import logging
from typing import Any

from app.services import receipt_service as _receipt_service
from app.services.receipt_image_preprocessing import preprocess_receipt_image_for_ocr

LOGGER = logging.getLogger(__name__)

_INSTALLED = False
_ORIGINAL_PADDLE = None
_ORIGINAL_TESSERACT = None


def _preprocess_safely(file_bytes: bytes, filename: str) -> bytes:
    try:
        output = preprocess_receipt_image_for_ocr(file_bytes)
        LOGGER.warning(
            'Receipt OCR preprocessing patch applied filename=%s input_bytes=%s output_bytes=%s',
            filename,
            len(file_bytes) if file_bytes else 0,
            len(output) if output else 0,
        )
        return output
    except Exception as exc:  # pragma: no cover
        LOGGER.exception('Receipt OCR preprocessing patch failed filename=%s error=%s', filename, exc)
        return file_bytes


def install_receipt_ocr_preprocessing_patch(*_: Any) -> bool:
    global _INSTALLED, _ORIGINAL_PADDLE, _ORIGINAL_TESSERACT
    if _INSTALLED:
        return False

    _ORIGINAL_PADDLE = getattr(_receipt_service, '_ocr_image_text_with_paddle', None)
    _ORIGINAL_TESSERACT = getattr(_receipt_service, '_ocr_image_text_with_tesseract', None)

    if callable(_ORIGINAL_PADDLE):
        def _ocr_image_text_with_paddle(file_bytes: bytes, filename: str):
            return _ORIGINAL_PADDLE(_preprocess_safely(file_bytes, filename), filename)

        _receipt_service._ocr_image_text_with_paddle = _ocr_image_text_with_paddle

    if callable(_ORIGINAL_TESSERACT):
        def _ocr_image_text_with_tesseract(file_bytes: bytes, filename: str):
            return _ORIGINAL_TESSERACT(_preprocess_safely(file_bytes, filename), filename)

        _receipt_service._ocr_image_text_with_tesseract = _ocr_image_text_with_tesseract

    _INSTALLED = True
    LOGGER.warning(
        'Receipt OCR preprocessing patch installed paddle=%s tesseract=%s',
        callable(_ORIGINAL_PADDLE),
        callable(_ORIGINAL_TESSERACT),
    )
    return True
