from __future__ import annotations

RECEIPT_EXPORT_FIXTURE_PERMISSION = "platform.test_fixtures.manage"
RECEIPT_EXPORT_FIXTURE_ROUTES = frozenset(
    {
        ("POST", "/api/testing/fixtures/receipt-export/generate"),
        ("GET", "/api/testing/fixtures/receipt-export/download"),
    }
)


def required_receipt_export_fixture_permission(method: str, path: str) -> str | None:
    request_key = (str(method or "").upper(), str(path or ""))
    if request_key not in RECEIPT_EXPORT_FIXTURE_ROUTES:
        return None
    return RECEIPT_EXPORT_FIXTURE_PERMISSION
