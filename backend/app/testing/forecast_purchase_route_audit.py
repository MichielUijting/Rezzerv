from __future__ import annotations

import argparse
import inspect
import json
import time
from pathlib import Path
from typing import Any

from app.main import app

TARGET_TERMS = (
    "almost-out",
    "almost_out",
    "prediction",
    "forecast",
    "prognos",
    "purchase",
    "procurement",
    "inkoop",
    "import-setting",
    "import_setting",
)
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
    "inventory_id",
    "batch_id",
    "line_id",
    "article_id",
)
MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


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
    lowered = str(path or "").lower()
    return any(term in lowered for term in TARGET_TERMS)


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
    without_auth = [
        f"{item['method']} {item['path']} :: {item['module']}.{item['endpoint']}"
        for item in rows
        if not item["authorization_parameter"] and not item["auth_markers"]
    ]
    mutation_without_auth = [
        f"{item['method']} {item['path']} :: {item['module']}.{item['endpoint']}"
        for item in mutations
        if not item["authorization_parameter"] and not item["auth_markers"]
    ]
    return {
        "audit_version": 1,
        "summary": {
            "route_registrations": len(rows),
            "reads": len(reads),
            "mutations": len(mutations),
            "routes_without_auth_marker": len(without_auth),
            "mutations_without_auth_marker": len(mutation_without_auth),
        },
        "routes_without_auth_marker": without_auth,
        "mutations_without_auth_marker": mutation_without_auth,
        "routes": rows,
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
    print("M2C2N_FORECAST_PURCHASE_ROUTE_AUDIT_GREEN")


if __name__ == "__main__":
    main()
