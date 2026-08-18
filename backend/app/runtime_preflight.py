"""Fail-closed startup preflight for heavyweight receipt runtime dependencies."""

from __future__ import annotations

import os

from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import (
    warm_receipt_image_preprocessing,
)


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _rembg_warmup_enabled() -> bool:
    return str(
        os.getenv("REZZERV_RECEIPT_STARTUP_REMBG_WARMUP", "true") or "true"
    ).strip().lower() in _TRUE_VALUES


def run_runtime_preflight() -> dict:
    """Warm rembg before Uvicorn starts so user requests never pay model download."""
    result = warm_receipt_image_preprocessing()
    print(f"Receipt image preprocessing startup warmup: {result}", flush=True)

    if _rembg_warmup_enabled() and str(result.get("status") or "") != "ok":
        raise RuntimeError(
            "Receipt image preprocessing warmup failed while "
            f"REZZERV_RECEIPT_STARTUP_REMBG_WARMUP is enabled: {result}"
        )
    return result


if __name__ == "__main__":
    run_runtime_preflight()
