"""Text extraction helpers for receipt parsing.

Compatibility façade: no behaviour is changed in Release 0. Functions are
re-exported from the legacy receipt service to prepare a safe split into smaller
services.
"""

from ....services.receipt_service import (  # noqa: F401
    _convert_webp_to_png_bytes,
    _extract_pdf_text,
    _extract_text_from_eml,
    _get_paddle_ocr,
    _html_to_text,
    _normalize_paddle_collection,
    _ocr_bbox_to_line_anchor,
    _ocr_image_text_with_paddle,
    _ocr_image_text_with_tesseract,
    _ocr_pdf_text_with_ocrmypdf,
)
