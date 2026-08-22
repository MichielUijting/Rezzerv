from __future__ import annotations

RECEIPT_STATUS_BASELINE_DIAGNOSTICS_PERMISSION = "platform.diagnostics.view"
RECEIPT_STATUS_BASELINE_TECHNICAL_PERMISSION = "platform.technical_configuration.manage"
RECEIPT_STATUS_BASELINE_REQUIRED_PERMISSIONS = (
    RECEIPT_STATUS_BASELINE_DIAGNOSTICS_PERMISSION,
    RECEIPT_STATUS_BASELINE_TECHNICAL_PERMISSION,
)
RECEIPT_STATUS_BASELINE_ROUTES = frozenset(
    {
        ("POST", "/api/admin/diagnose-receipt-status-baseline"),
        ("POST", "/api/admin/validate-receipt-status-baseline"),
    }
)


def required_receipt_status_baseline_permissions(method: str, path: str) -> tuple[str, ...]:
    request_key = (str(method or "").upper(), str(path or ""))
    if request_key not in RECEIPT_STATUS_BASELINE_ROUTES:
        return ()
    return RECEIPT_STATUS_BASELINE_REQUIRED_PERMISSIONS
