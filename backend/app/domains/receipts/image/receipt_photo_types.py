from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class ReceiptNormalizationResult:
    success: bool
    used_fallback: bool
    confidence: float
    reason: Optional[str]
    detected_as_photo: bool
    original_path: str
    normalized_path: Optional[str]
    ocr_ready_path: Optional[str]
    diagnostics: dict[str, Any] = field(default_factory=dict)
