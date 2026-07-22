from __future__ import annotations

import threading
import time
from collections.abc import Callable

from fastapi import HTTPException
from fastapi.responses import JSONResponse

PROTECTED_MUTATIONS = {
    ("POST", "/api/testing/diagnostics/store-location-options"),
    ("POST", "/api/testing/fixtures/browser-regression/reset"),
    ("POST", "/api/testing/fixtures/cleanup"),
    ("POST", "/api/testing/fixtures/inventory/ensure"),
    ("POST", "/api/testing/fixtures/receipt-export/generate"),
    ("POST", "/api/testing/fixtures/receipt-layer1/generate"),
    ("POST", "/api/testing/fixtures/receipts/seed-kassa"),
    ("POST", "/api/testing/regression/all/run"),
    ("POST", "/api/testing/regression/almost-out-prediction"),
    ("POST", "/api/testing/regression/almost-out-self-test"),
    ("POST", "/api/testing/regression/layer1/run"),
    ("POST", "/api/testing/regression/layer2/run"),
    ("POST", "/api/testing/regression/layer3/run"),
    ("POST", "/api/testing/regression/parsing-fixtures/run"),
    ("POST", "/api/testing/regression/parsing-raw/run"),
    ("POST", "/api/testing/regression/smoke/run"),
    ("POST", "/api/testing/reports/complete"),
    ("POST", "/api/admin/backfill-purchase-import-live-aliases"),
    ("POST", "/api/admin/diagnose-receipt-status-baseline"),
    ("POST", "/api/admin/external-relations/batch/decision"),
    ("POST", "/api/admin/inventory/groups/ensure-schema"),
    ("POST", "/api/admin/kassa-regression/run"),
    ("POST", "/api/admin/kassa-smoke/run"),
    ("POST", "/api/admin/product-groups/import-gpc-nl"),
    ("POST", "/api/admin/receipts/purge-archived"),
    ("POST", "/api/admin/recompute-receipt-statuses"),
    ("POST", "/api/admin/validate-receipt-status-baseline"),
}

_DIAGNOSIS_DUPLICATE_PATHS = {
    "/api/testing/receipt-parser-diagnosis",
    "/api/testing/receipt-parser-diagnosis/download",
}
_PREFERRED_DIAGNOSIS_MODULE = "app.api.receipt_diagnosis_routes"


def authorize_platform_admin_request(
    method: str,
    path: str,
    authorization: str | None,
    require_platform_admin_user: Callable[[str | None], object],
) -> object | None:
    request_key = (str(method or "").upper(), str(path or ""))
    if request_key not in PROTECTED_MUTATIONS:
        return None
    return require_platform_admin_user(authorization)


def deduplicate_receipt_parser_diagnosis_routes(app) -> int:
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


def _deduplicate_late_route_registrations(app) -> None:
    stable_rounds = 0
    previous_signature: tuple[tuple[str, str], ...] | None = None
    for _ in range(100):
        deduplicate_receipt_parser_diagnosis_routes(app)
        signature = tuple(
            sorted(
                (
                    str(getattr(route, "path", "") or ""),
                    str(getattr(getattr(route, "endpoint", None), "__module__", "") or ""),
                )
                for route in app.router.routes
                if str(getattr(route, "path", "") or "") in _DIAGNOSIS_DUPLICATE_PATHS
            )
        )
        if signature == previous_signature and len(signature) == len(_DIAGNOSIS_DUPLICATE_PATHS):
            stable_rounds += 1
            if stable_rounds >= 10:
                return
        else:
            previous_signature = signature
            stable_rounds = 0
        time.sleep(0.1)


def install_platform_admin_route_guard(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "platform_admin_route_guard_installed", False):
        return

    deduplicate_receipt_parser_diagnosis_routes(app)
    threading.Thread(
        target=_deduplicate_late_route_registrations,
        args=(app,),
        daemon=True,
    ).start()

    @app.middleware("http")
    async def platform_admin_route_guard(request, call_next):
        try:
            authorize_platform_admin_request(
                request.method,
                request.url.path,
                request.headers.get("authorization"),
                main_module.require_platform_admin_user,
            )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or None,
            )
        return await call_next(request)

    app.state.platform_admin_route_guard_installed = True
    app.state.receipt_admin_household_guard_installed = True
