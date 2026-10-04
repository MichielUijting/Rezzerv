from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.api import dashboard_routes


class _BeginContext:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def begin(self):
        return _BeginContext()


def _request(cookie: str | None = "session-token") -> Request:
    headers = []
    if cookie is not None:
        headers.append(
            (
                b"cookie",
                f"{dashboard_routes.SESSION_COOKIE_NAME}={cookie}".encode("ascii"),
            )
        )
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/dashboard",
            "headers": headers,
        }
    )


def _run_regular_context_check() -> None:
    captured: dict[str, str] = {}

    dashboard_routes.engine = _FakeEngine()
    dashboard_routes.resolve_server_session = lambda _conn, _raw: SimpleNamespace(
        context_type="regular",
        active_household_id="household-1",
        user_id="user-1",
    )

    def fake_dashboard(_conn, *, household_id, user_id):
        captured["household_id"] = household_id
        captured["user_id"] = user_id
        return {"status": {"shopping": 3}}

    dashboard_routes.build_household_dashboard = fake_dashboard
    payload = dashboard_routes.get_household_dashboard(_request())
    assert payload["status"]["shopping"] == 3
    assert captured == {"household_id": "household-1", "user_id": "user-1"}


def _run_non_regular_context_check(context_type: str) -> None:
    dashboard_routes.engine = _FakeEngine()
    dashboard_routes.resolve_server_session = lambda _conn, _raw: SimpleNamespace(
        context_type=context_type,
        active_household_id=None if context_type == "none" else "0",
        user_id="user-1",
    )
    try:
        dashboard_routes.get_household_dashboard(_request())
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "huishouden" in str(exc.detail).lower()
        return
    raise AssertionError(f"{context_type} context had 403 moeten geven")


def _run_missing_session_check() -> None:
    dashboard_routes.engine = _FakeEngine()

    def reject_missing_session(_conn, raw_session_id):
        assert raw_session_id is None
        raise HTTPException(status_code=401, detail="Geen geldige sessie")

    dashboard_routes.resolve_server_session = reject_missing_session
    try:
        dashboard_routes.get_household_dashboard(_request(cookie=None))
    except HTTPException as exc:
        assert exc.status_code == 401
        return
    raise AssertionError("Ontbrekende sessie had 401 moeten geven")


def main() -> int:
    original_engine = dashboard_routes.engine
    original_resolve = dashboard_routes.resolve_server_session
    original_build = dashboard_routes.build_household_dashboard

    try:
        _run_regular_context_check()
        _run_non_regular_context_check("none")
        _run_non_regular_context_check("system")
        _run_missing_session_check()
    finally:
        dashboard_routes.engine = original_engine
        dashboard_routes.resolve_server_session = original_resolve
        dashboard_routes.build_household_dashboard = original_build

    print("DASHBOARD_API_SELFTEST_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
