from __future__ import annotations

import inspect

from app.main import app


EXPECTED_SUPPORT_ROUTES = {
    ("POST", "/api/support/threads"): "household",
    ("GET", "/api/support/threads"): "household",
    ("GET", "/api/support/threads/{thread_id}"): "household",
    ("POST", "/api/support/threads/{thread_id}/messages"): "household",
    ("DELETE", "/api/support/threads/{thread_id}"): "household",
    ("GET", "/api/platform/support/threads"): "platform_read",
    ("GET", "/api/platform/support/threads/{thread_id}"): "platform_read",
    ("POST", "/api/platform/support/threads"): "platform_mutate",
    ("POST", "/api/platform/support/threads/{thread_id}/messages"): "platform_mutate",
    ("PATCH", "/api/platform/support/threads/{thread_id}/status"): "platform_mutate",
    ("DELETE", "/api/platform/support/threads/{thread_id}"): "platform_mutate",
    ("GET", "/api/platform/support/export.csv"): "platform_read",
}


def _support_routes():
    rows = {}
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        module = str(getattr(endpoint, "__module__", "") or "")
        if module != "app.api.support_message_routes":
            continue
        path = str(getattr(route, "path", "") or "")
        for method in sorted(str(value) for value in (getattr(route, "methods", None) or [])):
            if method in {"HEAD", "OPTIONS"}:
                continue
            key = (method, path)
            assert key not in rows, f"Dubbele supportroute: {method} {path}"
            rows[key] = endpoint
    return rows


def main() -> None:
    actual = _support_routes()
    assert set(actual) == set(EXPECTED_SUPPORT_ROUTES), {
        "missing": sorted(set(EXPECTED_SUPPORT_ROUTES) - set(actual)),
        "unexpected": sorted(set(actual) - set(EXPECTED_SUPPORT_ROUTES)),
    }

    for key, guard_type in EXPECTED_SUPPORT_ROUTES.items():
        endpoint = actual[key]
        signature = str(inspect.signature(endpoint)).lower()
        source = inspect.getsource(endpoint)
        assert "authorization" in signature, f"Authorization-header ontbreekt op {key}"

        if guard_type == "household":
            assert "_household_actor(authorization)" in source, f"Huishoudguard ontbreekt op {key}"
        elif guard_type == "platform_read":
            assert '_platform_actor(authorization, "platform.support_access.read")' in source, (
                f"Platform-readguard ontbreekt op {key}"
            )
        elif guard_type == "platform_mutate":
            assert '_platform_actor(authorization, "platform.support_access.mutate")' in source, (
                f"Platform-mutateguard ontbreekt op {key}"
            )
        else:
            raise AssertionError(f"Onbekend guardtype: {guard_type}")

    print("M2C2N_NOTIFICATION_ROUTE_CONTRACT_GREEN")


if __name__ == "__main__":
    main()
