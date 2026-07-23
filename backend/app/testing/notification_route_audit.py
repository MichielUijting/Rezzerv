from __future__ import annotations

import argparse
import inspect
import json
import time
from pathlib import Path
from typing import Any

from app.main import app

MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
TARGET_TERMS = (
    "notification",
    "notifications",
    "melding",
    "meldingen",
    "alert",
    "alerts",
)
AUTH_MARKERS = (
    "require_household_context",
    "require_household_admin_context",
    "require_inventory_write_context",
    "require_household_permission",
    "require_platform_admin_user",
    "get_request_household_id",
)
HOUSEHOLD_MARKERS = (
    "household_id",
    "active_household_id",
    "notification_id",
    "message_id",
    "user_id",
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


def endpoint_source(endpoint: Any) -> tuple[str, str | None, int | None]:
    try:
        source = inspect.getsource(endpoint)
    except (OSError, TypeError):
        source = ""
    try:
        source_file = inspect.getsourcefile(endpoint)
    except (OSError, TypeError):
        source_file = None
    try:
        first_line = inspect.getsourcelines(endpoint)[1]
    except (OSError, TypeError):
        first_line = None
    return source, source_file, first_line


def is_target_route(path: str, endpoint: Any, source: str) -> bool:
    endpoint_name = str(getattr(endpoint, "__qualname__", "") or "").lower()
    module_name = str(getattr(endpoint, "__module__", "") or "").lower()
    haystack = " ".join((path.lower(), endpoint_name, module_name, source.lower()))
    return any(term in haystack for term in TARGET_TERMS)


def audit_routes() -> dict[str, Any]:
    wait_for_stable_routes()
    rows: list[dict[str, Any]] = []
    for route in app.routes:
        path = str(getattr(route, "path", "") or "")
        endpoint = getattr(route, "endpoint", None)
        source, source_file, first_line = endpoint_source(endpoint)
        if not is_target_route(path, endpoint, source):
            continue
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
                    "matched_terms": [term for term in TARGET_TERMS if term in " ".join((path.lower(), str(getattr(endpoint, "__qualname__", "") or "").lower(), str(getattr(endpoint, "__module__", "") or "").lower(), lowered))],
                    "source": source,
                }
            )
    rows.sort(key=lambda item: (item["path"], item["method"], item["module"], item["endpoint"]))
    reads = [item for item in rows if item["access"] == "read"]
    mutations = [item for item in rows if item["access"] == "mutation"]
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
    print("M2C2N_NOTIFICATION_ROUTE_AUDIT_GREEN")


if __name__ == "__main__":
    main()
