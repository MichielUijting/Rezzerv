# CONTROL_BUILD_MARKER: Rezzerv-MVP-v01.12.76
# Compatibility package: keep existing imports stable while delegating to the PO-norm V4 service.
# Filename normalization treats .jpg and .jpeg receipt files as the same baseline source.
from __future__ import annotations

from app.services import receipt_status_baseline_service_v4 as _v4


def _normalize_text_with_jpg_jpeg_equivalence(value):
    normalized = ''.join(ch.lower() for ch in str(value or '').strip() if ch.isalnum())
    for suffix in ('jpeg', 'jpg'):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


_v4._normalize_text = _normalize_text_with_jpg_jpeg_equivalence

load_expected_receipt_statuses = _v4.load_expected_receipt_statuses
load_baseline_receipts = _v4.load_baseline_receipts
load_baseline_receipt_lines = _v4.load_baseline_receipt_lines
validate_receipt_status_baseline = _v4.validate_receipt_status_baseline
diagnose_receipt_status_baseline = _v4.diagnose_receipt_status_baseline
