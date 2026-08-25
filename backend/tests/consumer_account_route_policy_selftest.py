"""Validate the 9.3.3 consumer account API context boundary."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException

from app.api import consumer_account_routes as routes


def _expect_http_status(expected_status: int, fn) -> None:
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == expected_status, (
            f"verwacht HTTP {expected_status}, kreeg HTTP {exc.status_code}"
        )
        return
    raise AssertionError(f"verwacht HTTP {expected_status}, maar geen fout ontvangen")


def run() -> int:
    checks: list[str] = []

    matching_routes = [
        route
        for route in routes.router.routes
        if getattr(route, "path", None) == "/api/account/password"
        and "POST" in set(getattr(route, "methods", set()) or set())
    ]
    assert len(matching_routes) == 1
    checks.append("password_route_unique")

    original_resolver = routes.resolve_current_server_session
    try:
        routes.resolve_current_server_session = lambda: SimpleNamespace(
            context_type="system",
            user_id="system-user",
            session_id="system-session",
        )
        _expect_http_status(403, routes._require_regular_consumer_session)
        checks.append("system_context_rejected")

        routes.resolve_current_server_session = lambda: SimpleNamespace(
            context_type="none",
            user_id="none-user",
            session_id="none-session",
        )
        _expect_http_status(403, routes._require_regular_consumer_session)
        checks.append("none_context_rejected")

        regular_context = SimpleNamespace(
            context_type="regular",
            user_id="regular-user",
            session_id="regular-session",
        )
        routes.resolve_current_server_session = lambda: regular_context
        assert routes._require_regular_consumer_session() is regular_context
        checks.append("regular_context_allowed")
    finally:
        routes.resolve_current_server_session = original_resolver

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("CONSUMER_ACCOUNT_ROUTE_POLICY_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
