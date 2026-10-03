from types import SimpleNamespace

import pytest
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
        headers.append((b"cookie", f"{dashboard_routes.SESSION_COOKIE_NAME}={cookie}".encode("ascii")))
    return Request({"type": "http", "method": "GET", "path": "/api/dashboard", "headers": headers})


def test_dashboard_route_uses_regular_server_session_context(monkeypatch):
    captured = {}

    monkeypatch.setattr(dashboard_routes, "engine", _FakeEngine())
    monkeypatch.setattr(
        dashboard_routes,
        "resolve_server_session",
        lambda _conn, raw_session_id: SimpleNamespace(
            context_type="regular",
            active_household_id="household-1",
            user_id="user-1",
            raw_session_id=raw_session_id,
        ),
    )

    def fake_dashboard(_conn, *, household_id, user_id):
        captured["household_id"] = household_id
        captured["user_id"] = user_id
        return {"status": {"shopping": 3}, "generated_at": "2026-10-03T12:00:00+00:00"}

    monkeypatch.setattr(dashboard_routes, "build_household_dashboard", fake_dashboard)

    payload = dashboard_routes.get_household_dashboard(_request())

    assert payload["status"]["shopping"] == 3
    assert captured == {"household_id": "household-1", "user_id": "user-1"}


@pytest.mark.parametrize("context_type", ["none", "system"])
def test_dashboard_route_rejects_non_regular_context(monkeypatch, context_type):
    monkeypatch.setattr(dashboard_routes, "engine", _FakeEngine())
    monkeypatch.setattr(
        dashboard_routes,
        "resolve_server_session",
        lambda _conn, _raw_session_id: SimpleNamespace(
            context_type=context_type,
            active_household_id=None if context_type == "none" else "0",
            user_id="user-1",
        ),
    )

    with pytest.raises(HTTPException) as exc:
        dashboard_routes.get_household_dashboard(_request())

    assert exc.value.status_code == 403
    assert "huishouden" in str(exc.value.detail).lower()


def test_dashboard_route_preserves_session_401(monkeypatch):
    monkeypatch.setattr(dashboard_routes, "engine", _FakeEngine())

    def reject_missing_session(_conn, raw_session_id):
        assert raw_session_id is None
        raise HTTPException(status_code=401, detail="Geen geldige sessie")

    monkeypatch.setattr(dashboard_routes, "resolve_server_session", reject_missing_session)

    with pytest.raises(HTTPException) as exc:
        dashboard_routes.get_household_dashboard(_request(cookie=None))

    assert exc.value.status_code == 401


def test_dashboard_drilldown_route_uses_regular_server_session_context(monkeypatch):
    captured = {}

    monkeypatch.setattr(dashboard_routes, "engine", _FakeEngine())
    monkeypatch.setattr(
        dashboard_routes,
        "resolve_server_session",
        lambda _conn, _raw_session_id: SimpleNamespace(
            context_type="regular",
            active_household_id="household-1",
            user_id="user-1",
        ),
    )

    def fake_drilldown(
        _conn,
        *,
        household_id,
        user_id,
        metric,
        granularity,
        bucket_index,
        series,
        comparison,
    ):
        captured.update({
            "household_id": household_id,
            "user_id": user_id,
            "metric": metric,
            "granularity": granularity,
            "bucket_index": bucket_index,
            "series": series,
            "comparison": comparison,
        })
        return {"label": "W40 2026", "receipts": []}

    monkeypatch.setattr(dashboard_routes, "build_household_dashboard_drilldown", fake_drilldown)

    payload = dashboard_routes.get_household_dashboard_drilldown(
        _request(),
        metric="spend",
        granularity="weeks",
        bucket_index=3,
        series="previous",
        comparison="year",
    )

    assert payload["label"] == "W40 2026"
    assert captured == {
        "household_id": "household-1",
        "user_id": "user-1",
        "metric": "spend",
        "granularity": "weeks",
        "bucket_index": 3,
        "series": "previous",
        "comparison": "year",
    }
