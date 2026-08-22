from __future__ import annotations

FIXTURE_LIFECYCLE_PERMISSION = "platform.test_fixtures.manage"
FIXTURE_LIFECYCLE_ROUTES = frozenset(
    {
        ("POST", "/api/testing/diagnostics/store-location-options"),
        ("POST", "/api/testing/fixtures/browser-regression/reset"),
        ("POST", "/api/testing/fixtures/cleanup"),
        ("POST", "/api/testing/fixtures/inventory/ensure"),
        ("POST", "/api/testing/fixtures/receipt-layer1/generate"),
        ("POST", "/api/testing/fixtures/receipts/seed-kassa"),
    }
)


def required_fixture_lifecycle_permission(method: str, path: str) -> str | None:
    request_key = (str(method or "").upper(), str(path or ""))
    if request_key not in FIXTURE_LIFECYCLE_ROUTES:
        return None
    return FIXTURE_LIFECYCLE_PERMISSION
