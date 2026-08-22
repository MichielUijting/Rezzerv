from __future__ import annotations

KASSA_BACKGROUND_JOB_PERMISSION = "platform.background_jobs.manage"
KASSA_DIAGNOSTICS_VIEW_PERMISSION = "platform.diagnostics.view"

KASSA_RUN_ROUTES = frozenset(
    {
        ("POST", "/api/admin/kassa-regression/run"),
        ("POST", "/api/admin/kassa-smoke/run"),
    }
)
KASSA_STATUS_ROUTES = frozenset(
    {
        ("GET", "/api/admin/kassa-regression/status"),
        ("GET", "/api/admin/kassa-smoke/status"),
    }
)
KASSA_DIAGNOSTIC_ROUTE_PERMISSIONS = {
    **{route: KASSA_BACKGROUND_JOB_PERMISSION for route in KASSA_RUN_ROUTES},
    **{route: KASSA_DIAGNOSTICS_VIEW_PERMISSION for route in KASSA_STATUS_ROUTES},
}


def required_kassa_diagnostic_permission(method: str, path: str) -> str | None:
    request_key = (str(method or "").upper(), str(path or ""))
    return KASSA_DIAGNOSTIC_ROUTE_PERMISSIONS.get(request_key)
