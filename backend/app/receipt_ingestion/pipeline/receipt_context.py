"""Read-only receipt parse context boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReceiptSourceContext:
    filename: str
    mime_type: str | None = None
    source_kind: str | None = None