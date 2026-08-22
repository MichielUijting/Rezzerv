from __future__ import annotations

MAINTENANCE_RECOMPUTE_PERMISSION = "platform.background_jobs.manage"
MAINTENANCE_RECOMPUTE_ROUTES = frozenset(
    {
        ("POST", "/api/admin/backfill-purchase-import-live-aliases"),
        ("POST", "/api/admin/recompute-receipt-statuses"),
    }
)


def required_maintenance_recompute_permission(method: str, path: str) -> str | None:
    request_key = (str(method or "").upper(), str(path or ""))
    if request_key not in MAINTENANCE_RECOMPUTE_ROUTES:
        return None
    return MAINTENANCE_RECOMPUTE_PERMISSION
