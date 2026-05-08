from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image, ImageOps

LOGGER = logging.getLogger(__name__)

DEBUG_DIR = Path('/app/data/receipts/debug')
DEBUG_OUTPUT_PATH = DEBUG_DIR / 'latest-ocr-preprocessed.png'
DEBUG_ORIGINAL_PATH = DEBUG_DIR / 'latest-ocr-00-original.png'
DEBUG_FINAL_PATH = DEBUG_DIR / 'latest-ocr-02-final.png'


def _encode_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def _write_debug_png(path: Path, image: Image.Image, reason: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_encode_png(image))
        LOGGER.warning(
            'Receipt preprocessing DEBUG_WRITE path=%s reason=%s size=%sx%s',
            path,
            reason,
            image.width,
            image.height,
        )
    except Exception as exc:
        LOGGER.warning('Receipt preprocessing DEBUG_WRITE_FAILED path=%s reason=%s error=%s', path, reason, exc)


def preprocess_receipt_image_for_ocr(file_bytes: bytes) -> bytes:
    """SSOT-safe stap 1: normaliseer alleen EXIF-orientatie vóór OCR.

    Deze functie wijzigt uitsluitend de afbeelding die aan OCR wordt aangeboden.
    Zij bepaalt geen kassabonstatus, past geen parsernorm toe, wijzigt geen
    receipt_lines-schema en bevat geen categorielogica. De status-SSOT blijft
    receipt_status_baseline_service_v4.py.
    """
    LOGGER.warning('Receipt preprocessing PIPELINE_ENTER variant=exif-normalize-v1 bytes=%s', len(file_bytes) if file_bytes else 0)
    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            original = image.copy()
            normalized = ImageOps.exif_transpose(image).convert('RGB')
            _write_debug_png(DEBUG_ORIGINAL_PATH, original.convert('RGB'), 'exif-normalize-v1:original')
            _write_debug_png(DEBUG_FINAL_PATH, normalized, 'exif-normalize-v1:final')
            _write_debug_png(DEBUG_OUTPUT_PATH, normalized, 'exif-normalize-v1:ocr-input-alias')
            LOGGER.warning(
                'Receipt preprocessing PIPELINE_EXIT method=exif_transpose original_size=%sx%s output_size=%sx%s',
                original.width,
                original.height,
                normalized.width,
                normalized.height,
            )
            return _encode_png(normalized)
    except Exception as exc:
        LOGGER.exception('Receipt preprocessing PIPELINE_EXCEPTION method=exif_transpose error=%s', exc)
        return file_bytes
