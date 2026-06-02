from __future__ import annotations

# R9-38C1a:
# Backwards-compatible wrapper. PLUS-specific runtime correction logic has moved
# to app.receipt_ingestion.profiles.plus.corrections.
# Remove this wrapper after receipt_service.py imports the PLUS profile directly.

from app.receipt_ingestion.profiles.plus.corrections import apply_plus_runtime_corrections

__all__ = ["apply_plus_runtime_corrections"]
