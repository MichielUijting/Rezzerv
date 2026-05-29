from __future__ import annotations

"""Deprecated receipt OCR preprocessing monkeypatch.

R9-36N:
This module intentionally no longer monkeypatches ``app.services.receipt_service``.

The previous implementation replaced ``_ocr_image_text_with_paddle`` and
``_ocr_image_text_with_tesseract`` at runtime. That made receipt parser behavior
import-order dependent: importing ``app.main`` could produce different parsing
results from importing and calling ``parse_receipt_content`` directly.

Receipt image preprocessing must remain explicit inside the normal parser flow
(``parse_receipt_content`` / ``apply_receipt_image_preprocessing``), not as a
package-level runtime mutation.
"""

from typing import Any

_INSTALLED = False


def install_receipt_ocr_preprocessing_patch(*_: Any) -> bool:
    """Compatibility no-op.

    Keep the public function so old startup code can still call it safely, but do
    not mutate receipt_service. Returning False signals that no patch was
    installed.
    """
    return False
