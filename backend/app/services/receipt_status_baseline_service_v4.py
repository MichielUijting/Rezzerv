"""Compatibility shim for legacy imports after Baseline V7 switch.

R9-36I removed the obsolete V6/V4 implementation, but one diagnostic route
still imported this historic module path at startup. This file intentionally
contains no old baseline logic or data; it only forwards to the active V7
receipt status baseline service so FastAPI can start while remaining on the
single active baseline implementation.
"""

from app.services.receipt_status_baseline_service import (  # noqa: F401
    diagnose_receipt_status_baseline,
    validate_receipt_status_baseline,
)
