"""Fail-closed startup preflight for heavyweight receipt runtime dependencies."""

from __future__ import annotations

import os

from app.receipt_ingestion.preprocessing.receipt_image_preprocessing import (
    warm_receipt_image_preprocessing,
)
from app.receipt_ingestion.service_parts.image_ocr_flow import (
    warm_receipt_ocr_runtime,
)


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _rembg_warmup_enabled() -> bool:
    return str(
        os.getenv("REZZERV_RECEIPT_STARTUP_REMBG_WARMUP", "true") or "true"
    ).strip().lower() in _TRUE_VALUES


def _paddle_warmup_enabled() -> bool:
    return str(
        os.getenv("REZZERV_RECEIPT_STARTUP_PADDLE_WARMUP", "true") or "true"
    ).strip().lower() in _TRUE_VALUES


def run_runtime_preflight() -> dict:
    """Warm receipt image/OCR models before Uvicorn accepts user requests.

    A first receipt upload may never determine parser quality merely because the
    Paddle model is still cold. The preflight therefore makes both rembg and the
    primary Paddle OCR runtime ready before backend health can become green.
    """
    image_result = warm_receipt_image_preprocessing()
    print(f"Receipt image preprocessing startup warmup: {image_result}", flush=True)

    if _rembg_warmup_enabled() and str(image_result.get("status") or "") != "ok":
        raise RuntimeError(
            "Receipt image preprocessing warmup failed while "
            f"REZZERV_RECEIPT_STARTUP_REMBG_WARMUP is enabled: {image_result}"
        )

    ocr_result = warm_receipt_ocr_runtime()
    print(f"Receipt OCR startup warmup: {ocr_result}", flush=True)
    if _paddle_warmup_enabled() and not bool(ocr_result.get("paddle_ready")):
        raise RuntimeError(
            "Receipt Paddle OCR warmup failed while "
            f"REZZERV_RECEIPT_STARTUP_PADDLE_WARMUP is enabled: {ocr_result}"
        )

    # Preserve the historical top-level rembg result contract while exposing
    # the OCR readiness evidence as an additional diagnostic field.
    result = dict(image_result)
    result["ocr_runtime"] = dict(ocr_result)
    return result


if __name__ == "__main__":
    run_runtime_preflight()
