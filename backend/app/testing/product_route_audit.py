from __future__ import annotations

import argparse
import inspect
import json
import time
from pathlib import Path
from typing import Any

import app.main as main_module
from app.main import app


TARGET_PREFIXES = (
    "/api/household-articles/",
    "/api/products/",
    "/api/product-identities/",
    "/api/product-groups",
    "/api/inventory/groups",
    "/api/external-products/",
    "/api/external-databases/catalog/products",
    "/api/purchase-import-lines/",
)
TARGET_EXACT_PATHS = {
    "/api/inventory/{inventory_id}/article-detail",
    "/api/inventory/{inventory_id}/external-product-link",
    "/api/inventory/items/{inventory_id}/group",
    "/api/external-databases/catalog/promote-candidate-with-product-type",
    "/api/store-review-articles",
}
EXCLUDED_PATH_PARTS = {
    "/article-group",
    "/api/article-groups",
}
AUTH_MARKERS = (
    "require_household_context",
    "require_inventory_write_context",
    "require_household_admin_context",
    "require_household_permission",
    "require_platform_admin_user",
    "get_request_household_id",
)
HOUSEHOLD_MARKERS = (
    "household_id",
    "active_household_id",
    "household_article_id",
    "inventory_id",
    "batch_id",
    "line_id",
    "global_product_id",
)
MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
DEPENDENCY_NAMES = (
    "get_store_review_article_options",
    "get_household_article_row_by_id",
)


def wait_for_stable_routes() -> None:
    previous: tuple[tuple[str, tuple[str, ...]], ...] | None = None
    stable_rounds = 0
    for _ in range(200):
        signature = tuple(
            sorted(
                (
                    str(getattr(route, "path", "") or ""),
                    tuple(sorted(str(method) for method in (getattr(route, "methods", None) or []))),
                )
                for route in app.routes
            )
        )
        if signature == previous:
            stable_rounds += 1
            if stable_rounds >= 10:
                return
        else:
            previous = signature
            stable_rounds = 0
        time.sleep(0.1)
    raise RuntimeError("FastAPI-routeset werd niet stabiel")


def is_target_path(path: str) -> bool:
    if path in TARGET_EXACT_PATHS:
        return True
    if any(part in path for part in EXCLUDED_PATH_PARTS):
        return False
    return any(path.startswith(prefix) for prefix in TARGET_PREFIXES)


def endpoint_source(endpoint: Any) -> tuple[str, str | None, int | None]:
    try:
        source = inspect.getsource(endpoint)
    except (OSError, TypeError):
        source = ""
    try:
        file_name = inspect.getsourcefile(endpoint)
    except (OSError, TypeError):
        file_name = None
    try:
        first_line = inspect.getsourcelines(endpoint)[1]
    except (OSError, TypeError):
        first_line = None
    return source, file_name, first_line


def dependency_sources() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in DEPENDENCY_NAMES:
        value = getattr(main_module, name, None)
        source, source_file, first_line = endpoint_source(value)
        result[name] = {
            "source_file": source_file,
            "first_line": first_line,
            "source": source,
        }
    return result


def audit_routes() -> dict[str, Any]:
    wait_for_stable_routes()
    rows: list[dict[str, Any]] = []
    for route in app.routes:
        path = str(getattr(route, "path", "") or "")
        if not is_target_path(path):
            continue
        endpoint = getattr(route, "endpoint", None)
        source, source_file, first_line = endpoint_source(endpoint)
        lowered = source.lower()
        signature = str(inspect.signature(endpoint)) if endpoint is not None else ""
        for method in sorted(str(item) for item in (getattr(route, "methods", None) or [])):
            if method in {"HEAD", "OPTIONS"}:
                continue
            rows.append(
                {
                    "method": method,
                    "path": path,
                    "access": "mutation" if method in MUTATION_METHODS else "read",
                    "endpoint": str(getattr(endpoint, "__qualname__", "") or ""),
                    "module": str(getattr(endpoint, "__module__", "") or ""),
                    "signature": signature,
                    "source_file": source_file,
                    "first_line": first_line,
                    "authorization_parameter": "authorization" in signature.lower(),
                    "auth_markers": [marker for marker in AUTH_MARKERS if marker.lower() in lowered],
                    "household_markers": [marker for marker in HOUSEHOLD_MARKERS if marker.lower() in lowered],
                    "source": source,
                }
            )
    rows.sort(key=lambda item: (item["path"], item["method"], item["module"], item["endpoint"]))
    mutations = [item for item in rows if item["access"] == "mutation"]
    reads = [item for item in rows if item["access"] == "read"]
    mutation_without_auth_marker = [
        f"{item['method']} {item['path']} :: {item['module']}.{item['endpoint']}"
        for item in mutations
        if not item["authorization_parameter"] and not item["auth_markers"]
    ]
    return {
        "audit_version": 2,
        "summary": {
            "route_registrations": len(rows),
            "reads": len(reads),
            "mutations": len(mutations),
            "mutation_without_auth_marker": len(mutation_without_auth_marker),
        },
        "mutation_without_auth_marker": mutation_without_auth_marker,
        "routes": rows,
        "dependency_sources": dependency_sources(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = audit_routes()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))
    print("M2C2N_PRODUCT_ROUTE_AUDIT_GREEN")


if __name__ == "__main__":
    main()
