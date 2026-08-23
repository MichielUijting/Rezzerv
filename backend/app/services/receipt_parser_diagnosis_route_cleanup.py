from __future__ import annotations


_DIAGNOSIS_DUPLICATE_PATHS = {
    "/api/testing/receipt-parser-diagnosis",
    "/api/testing/receipt-parser-diagnosis/download",
}
_PREFERRED_DIAGNOSIS_MODULE = "app.api.receipt_diagnosis_routes"


def deduplicate_receipt_parser_diagnosis_routes(app) -> int:
    """Remove legacy duplicate receipt-parser diagnosis routes.

    The active source registration is unique in ``app.api.router``. This
    defensive one-shot cleanup remains for compatibility with older app
    assemblies that may preload both diagnosis routers.
    """

    removed = 0
    next_routes = []
    preferred_seen: set[str] = set()
    for route in app.router.routes:
        path = str(getattr(route, "path", "") or "")
        if path not in _DIAGNOSIS_DUPLICATE_PATHS:
            next_routes.append(route)
            continue
        endpoint = getattr(route, "endpoint", None)
        module = str(getattr(endpoint, "__module__", "") or "")
        if module == _PREFERRED_DIAGNOSIS_MODULE and path not in preferred_seen:
            preferred_seen.add(path)
            next_routes.append(route)
        else:
            removed += 1
    app.router.routes = next_routes
    return removed
