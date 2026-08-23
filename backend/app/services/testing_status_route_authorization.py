from __future__ import annotations


TESTING_STATUS_PERMISSION = "platform.diagnostics.view"
TESTING_STATUS_ROUTES = frozenset(
    {
        ("GET", "/api/testing/status"),
    }
)


def required_testing_status_permission(method: str, path: str) -> str | None:
    request_key = (str(method or "").upper(), str(path or ""))
    if request_key not in TESTING_STATUS_ROUTES:
        return None
    return TESTING_STATUS_PERMISSION
