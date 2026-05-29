from __future__ import annotations

"""Deprecated receipt store-detection monkeypatch.

R9-36N4:
This module must not mutate ``app.services.receipt_service`` at import time.
Store-detection improvements belong in ``app.receipt_ingestion.header_parser`` or
an explicitly called store-detection service, not in a runtime patch module.
"""

from typing import Any


def install_receipt_store_detection_patch(*_: Any) -> bool:
    """Compatibility no-op: do not replace receipt_service._store_from_text."""
    return False
