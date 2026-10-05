from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

from fastapi import Request
from starlette.routing import Match

from app.api import receipt_ah_oauth_proxy_routes as oauth
from app.integrations.retailer_accounts.ah import AHAccountSession


def _request(
    *,
    host: str = "localhost",
    port: int = 5174,
    cookie: str = "",
    extra_headers: dict[str, str] | None = None,
) -> Request:
    headers = [(b"host", f"{host}:{port}".encode("ascii"))]
    if cookie:
        headers.append((b"cookie", cookie.encode("ascii")))
    for name, value in (extra_headers or {}).items():
        headers.append((name.lower().encode("ascii"), value.encode("ascii")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/receipts/retailers/ah/connect",
        "raw_path": b"/api/receipts/retailers/ah/connect",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": (host, port),
    }
    return Request(scope)


def test_create_flow_uses_backend_public_port_and_same_host_return(monkeypatch) -> None:
    oauth.reset_ah_oauth_flows_for_tests()
    monkeypatch.delenv("REZZERV_BACKEND_PUBLIC_URL", raising=False)
    monkeypatch.setenv("REZZERV_BACKEND_PUBLIC_PORT", "8011")
    request = _request(host="inhuis.local")

    flow = oauth.create_ah_oauth_flow(
        request,
        household_id="household-1",
        return_to="http://inhuis.local:5174/instellingen/winkelkoppelingen",
    )

    assert flow.household_id == "household-1"
    assert flow.backend_origin == "http://inhuis.local:8011"
    assert flow.return_to == "http://inhuis.local:5174/instellingen/winkelkoppelingen"
    assert oauth.get_ah_oauth_flow(flow.flow_id) == flow
    assert oauth.build_ah_oauth_launch_url(flow).startswith(
        "http://inhuis.local:8011/ah-oauth/launch/"
    )


def test_cross_host_return_url_is_rejected(monkeypatch) -> None:
    oauth.reset_ah_oauth_flows_for_tests()
    monkeypatch.setenv("REZZERV_APP_BASE_URL", "http://localhost:5174")
    request = _request(host="inhuis.local")

    flow = oauth.create_ah_oauth_flow(
        request,
        household_id="household-1",
        return_to="https://attacker.example/instellingen/winkelkoppelingen",
    )

    assert flow.return_to == "http://localhost:5174/instellingen/winkelkoppelingen"


def test_launch_sets_short_lived_httponly_flow_cookie(monkeypatch) -> None:
    oauth.reset_ah_oauth_flows_for_tests()
    monkeypatch.setenv("REZZERV_BACKEND_PUBLIC_PORT", "8011")
    flow = oauth.create_ah_oauth_flow(_request(), household_id="household-1")

    response = asyncio.run(oauth.launch_ah_oauth(flow.flow_id))

    assert response.status_code == 302
    assert response.headers["location"].startswith("/login?")
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["client_id"] == ["appie-ios"]
    assert query["redirect_uri"] == ["appie://login-exit"]
    cookie = response.headers["set-cookie"].lower()
    assert "inhuis_ah_oauth_flow=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_proxy_route_never_matches_inhuis_api_or_control_paths() -> None:
    proxy_route = next(
        route for route in oauth.router.routes
        if getattr(route, "path", "") == "/{path:ahproxy}"
    )

    def match_for(path: str) -> Match:
        scope = {
            "type": "http",
            "method": "POST",
            "path": path,
            "root_path": "",
            "headers": [],
        }
        return proxy_route.matches(scope)[0]

    assert match_for("/login") == Match.FULL
    assert match_for("/assets/app.js") == Match.FULL
    assert match_for("/api/auth/login") == Match.NONE
    assert match_for("/api/auth/register") == Match.NONE
    assert match_for("/api/platform/primary-color") == Match.NONE
    assert match_for("/ah-oauth/callback") == Match.NONE
    assert match_for("/openapi.json") == Match.NONE
    assert match_for("/docs") == Match.NONE


def test_proxy_preserves_browser_headers_needed_by_login_controls() -> None:
    request = _request(
        host="localhost",
        port=8011,
        cookie="inhuis_ah_oauth_flow=secret; ah_session=kept",
        extra_headers={
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br",
            "content-length": "123",
            "origin": "http://localhost:8011",
            "referer": "http://localhost:8011/login?client_id=appie-ios",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-ch-ua": '"Chromium";v="140"',
            "x-requested-with": "fetch",
        },
    )

    headers = oauth.build_ah_forward_headers(
        request,
        backend_origin="http://localhost:8011",
    )

    assert headers["accept"] == "application/json"
    assert headers["sec-fetch-site"] == "same-origin"
    assert headers["sec-fetch-mode"] == "cors"
    assert headers["sec-ch-ua"] == '"Chromium";v="140"'
    assert headers["x-requested-with"] == "fetch"
    assert headers["origin"] == "https://login.ah.nl"
    assert headers["referer"] == "https://login.ah.nl/login?client_id=appie-ios"
    assert headers["cookie"] == "ah_session=kept"
    assert "host" not in headers
    assert "accept-encoding" not in headers
    assert "content-length" not in headers
    assert "inhuis_ah_oauth_flow" not in headers["cookie"]


def test_proxy_rewrites_appie_callback_and_sanitizes_login_cookie() -> None:
    body = (
        b'<a href="appie://login-exit?code=abc">done</a>'
        b'<script src="https://login.ah.nl/assets/app.js"></script>'
    )
    rewritten = oauth.rewrite_ah_oauth_body(
        body,
        backend_origin="http://localhost:8011",
    )

    assert b"http://localhost:8011/ah-oauth/callback?code=abc" in rewritten
    assert b"http://localhost:8011/assets/app.js" in rewritten

    cookie = oauth.sanitize_ah_set_cookie(
        "session=abc; Path=/; Secure; HttpOnly; SameSite=None; Domain=login.ah.nl"
    )
    assert cookie == "session=abc; Path=/; HttpOnly"


def test_callback_exchanges_code_and_persists_session_for_bound_household(monkeypatch) -> None:
    oauth.reset_ah_oauth_flows_for_tests()
    monkeypatch.setenv("REZZERV_BACKEND_PUBLIC_PORT", "8011")
    flow = oauth.create_ah_oauth_flow(
        _request(host="localhost"),
        household_id="household-bound",
        return_to="http://localhost:5174/instellingen/winkelkoppelingen",
    )

    seen: dict[str, object] = {}

    class FakeClient:
        def exchange_code(self, code: str) -> AHAccountSession:
            seen["code"] = code
            return AHAccountSession("access-secret", "refresh-secret")

        def close(self) -> None:
            seen["closed"] = True

    def fake_save_session(engine, household_id: str, session: AHAccountSession) -> None:
        seen["engine"] = engine
        seen["household_id"] = household_id
        seen["session"] = session

    monkeypatch.setattr(oauth, "AHReceiptClient", FakeClient)
    monkeypatch.setattr(oauth, "save_ah_session", fake_save_session)

    request = _request(
        host="localhost",
        port=8011,
        cookie=f"inhuis_ah_oauth_flow={flow.flow_id}",
    )
    response = asyncio.run(oauth.ah_oauth_callback(request, code="one-time-code"))

    assert response.status_code == 302
    assert response.headers["location"].endswith(
        "/instellingen/winkelkoppelingen?ah=connected"
    )
    assert seen["code"] == "one-time-code"
    assert seen["household_id"] == "household-bound"
    assert seen["session"] == AHAccountSession("access-secret", "refresh-secret")
    assert seen["closed"] is True
    assert oauth.get_ah_oauth_flow(flow.flow_id) is None
    assert "inhuis_ah_oauth_flow=" in response.headers["set-cookie"].lower()
