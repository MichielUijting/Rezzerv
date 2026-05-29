from __future__ import annotations

"""Deprecated receipt rotation monkeypatch.

R9-36N4:
This module must not replace ``receipt_service.parse_receipt_content`` at import
time. Receipt rotation or deskewing, if still required, must be implemented as an
explicit image-preprocessing step inside the normal receipt ingestion flow.
"""

from typing import Any


def install_receipt_rotation_patch(*_: Any) -> bool:
    """Compatibility no-op: do not mutate receipt parser runtime."""
    return False
