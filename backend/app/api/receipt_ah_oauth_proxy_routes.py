"""Temporary browser OAuth proxy for the Albert Heijn account connector.

AH only accepts the custom app redirect appie://login-exit. Inhuis cannot
receive that URI directly in a normal browser, so an authenticated API call
creates a short-lived, opaque flow. The browser then visits the backend origin,
which reverse-proxies login.ah.nl at the root so relative login assets keep
working. The appie redirect is rewritten to an Inhuis callback, after which the
existing encrypted household-scoped credential store is used.

The short-lived flow registry deliberately contains no AH credentials.
A backend restart during login invalidates the flow; the user can simply retry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import os
import secrets
from threading import RLock
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from starlette.convertors import Convertor, register_url_convertor

from app.db import engine
from app.integrations.retailer_accounts.ah import (
    AH_CLIENT_ID,
    AH_LOGIN_BASE_URL,
    AH_REDIRECT_URI,
    AHReceiptClient,
)
from app.services.retailer_account_secure_store import save_ah_session

class _AHProxyPathConvertor(Convertor):
    # The OAuth proxy is intentionally root-relative for AH login assets, but it
    # must never be eligible for Inhuis API/control/documentation routes. Keeping
    # those paths outside the route regex prevents the catch-all from shadowing
    # canonical endpoints even if router ordering changes.
    regex = r"(?!(?:api|ah-oauth)(?:/|$)|(?:docs|redoc)(?:/|$)|openapi\.json$).+"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return str(value)


register_url_convertor("ahproxy", _AHProxyPathConvertor())
router = APIRouter()
logger = logging.getLogger(__name__)

_FLOW_COOKIE = "inhuis_ah_oauth_flow"
_FLOW_TTL = timedelta(minutes=5)
_DEFAULT_BACKEND_PUBLIC_PORT = "8011"


@dataclass(frozen=True)
class AHOAuthFlow:
    flow_id: str
    household_id: str
    backend_origin: str
    return_to: str
    expires_at: datetime

    def expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


_flow_lock = RLock()
_flows: dict[str, AHOAuthFlow] = {}


def _clean_expired_flows() -> None:
    with _flow_lock:
        expired = [flow_id for flow_id, flow in _flows.items() if flow.expired()]
        for flow_id in expired:
            _flows.pop(flow_id, None)


def _format_host(hostname: str) -> str:
    return f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname


def resolve_backend_public_origin(request: Request) -> str:
    configured = str(os.getenv("REZZERV_BACKEND_PUBLIC_URL", "") or "").strip().rstrip("/")
    if configured:
        parsed = urlparse(configured)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError("REZZERV_BACKEND_PUBLIC_URL is ongeldig")
        return configured

    forwarded_host = str(request.headers.get("x-forwarded-host") or request.headers.get("host") or "").strip()
    hostname = forwarded_host.split(":", 1)[0].strip("[]") if forwarded_host else (request.url.hostname or "")
    if not hostname:
        raise RuntimeError("Backend-host voor AH-login kon niet worden bepaald")

    scheme = str(request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",", 1)[0].strip()
    if scheme not in {"http", "https"}:
        scheme = "http"
    public_port = str(os.getenv("REZZERV_BACKEND_PUBLIC_PORT", _DEFAULT_BACKEND_PUBLIC_PORT) or "").strip()
    if not public_port.isdigit():
        raise RuntimeError("REZZERV_BACKEND_PUBLIC_PORT is ongeldig")
    return f"{scheme}://{_format_host(hostname)}:{public_port}"


def _safe_return_to(request: Request, return_to: str | None) -> str:
    candidate = str(return_to or "").strip()
    request_host = str(request.headers.get("x-forwarded-host") or request.headers.get("host") or "").strip()
    request_hostname = request_host.split(":", 1)[0].strip("[]").lower()
    if candidate:
        parsed = urlparse(candidate)
        if (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.hostname.lower() == request_hostname
            and parsed.path == "/instellingen/winkelkoppelingen"
        ):
            return candidate
    app_origin = str(os.getenv("REZZERV_APP_BASE_URL", "http://localhost:5174") or "").strip().rstrip("/")
    return f"{app_origin}/instellingen/winkelkoppelingen"


def create_ah_oauth_flow(
    request: Request,
    *,
    household_id: str,
    return_to: str | None = None,
) -> AHOAuthFlow:
    _clean_expired_flows()
    flow = AHOAuthFlow(
        flow_id=secrets.token_urlsafe(32),
        household_id=str(household_id),
        backend_origin=resolve_backend_public_origin(request),
        return_to=_safe_return_to(request, return_to),
        expires_at=datetime.now(timezone.utc) + _FLOW_TTL,
    )
    with _flow_lock:
        _flows[flow.flow_id] = flow
    return flow


def get_ah_oauth_flow(flow_id: str | None) -> AHOAuthFlow | None:
    _clean_expired_flows()
    key = str(flow_id or "").strip()
    if not key:
        return None
    with _flow_lock:
        flow = _flows.get(key)
    if flow is None or flow.expired():
        return None
    return flow


def consume_ah_oauth_flow(flow_id: str) -> AHOAuthFlow | None:
    with _flow_lock:
        flow = _flows.pop(str(flow_id or "").strip(), None)
    if flow is None or flow.expired():
        return None
    return flow


def build_ah_oauth_launch_url(flow: AHOAuthFlow) -> str:
    return f"{flow.backend_origin}/ah-oauth/launch/{flow.flow_id}"


def _login_query() -> str:
    return urlencode(
        {
            "client_id": AH_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": AH_REDIRECT_URI,
        }
    )


def sanitize_ah_set_cookie(value: str) -> str:
    parts = str(value or "").split(";")
    if not parts:
        return ""
    kept = [parts[0]]
    for raw in parts[1:]:
        attr = raw.strip()
        lower = attr.lower()
        if lower == "secure" or lower.startswith("samesite=") or lower.startswith("domain="):
            continue
        kept.append(attr)
    return "; ".join(part for part in kept if part)


def rewrite_ah_oauth_body(body: bytes, *, backend_origin: str) -> bytes:
    return (
        body.replace(AH_REDIRECT_URI.encode("utf-8"), f"{backend_origin}/ah-oauth/callback".encode("utf-8"))
        .replace(AH_LOGIN_BASE_URL.encode("utf-8"), backend_origin.encode("utf-8"))
    )


def _rewrite_location(location: str, *, backend_origin: str) -> str:
    value = str(location or "")
    if value.startswith(AH_REDIRECT_URI):
        parsed = urlparse(value)
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{backend_origin}/ah-oauth/callback{query}"
    if value.startswith(AH_LOGIN_BASE_URL):
        return backend_origin + value[len(AH_LOGIN_BASE_URL):]
    return value


def _clean_forward_cookie(cookie_header: str) -> str:
    pairs = []
    for raw in str(cookie_header or "").split(";"):
        part = raw.strip()
        if not part:
            continue
        name = part.split("=", 1)[0].strip()
        if name == _FLOW_COOKIE:
            continue
        pairs.append(part)
    return "; ".join(pairs)


_REQUEST_HEADER_EXCLUDE = {
    "host",
    "content-length",
    "connection",
    "proxy-connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "accept-encoding",
    "cookie",
}


def build_ah_forward_headers(request: Request, *, backend_origin: str) -> dict[str, str]:
    # Keep the browser request as intact as possible. AH's login page includes
    # anti-bot/captcha requests whose browser/client-hint headers matter. This
    # mirrors the proven ah-mcp reverse-proxy behaviour: only transport-specific
    # headers and our own flow cookie are removed, while Origin/Referer are
    # rewritten to the real AH login origin.
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in _REQUEST_HEADER_EXCLUDE
    }

    cookie_header = _clean_forward_cookie(request.headers.get("cookie", ""))
    if cookie_header:
        headers["cookie"] = cookie_header

    if request.headers.get("origin"):
        headers["origin"] = AH_LOGIN_BASE_URL

    referer = str(request.headers.get("referer") or "")
    if referer:
        if referer.startswith(backend_origin):
            referer = AH_LOGIN_BASE_URL + referer[len(backend_origin):]
        else:
            referer = AH_LOGIN_BASE_URL + "/"
        headers["referer"] = referer

    return headers


def _return_with_status(flow: AHOAuthFlow, status: str) -> str:
    parsed = urlparse(flow.return_to)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["ah"] = status
    return urlunparse(parsed._replace(query=urlencode(query)))


@router.get("/ah-oauth/launch/{flow_id}", include_in_schema=False)
async def launch_ah_oauth(flow_id: str):
    flow = get_ah_oauth_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=410, detail="AH-login is verlopen. Start de koppeling opnieuw.")
    response = RedirectResponse(url=f"/login?{_login_query()}", status_code=302)
    response.set_cookie(
        _FLOW_COOKIE,
        flow.flow_id,
        max_age=int(_FLOW_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=flow.backend_origin.startswith("https://"),
        path="/",
    )
    return response


@router.get("/ah-oauth/callback", include_in_schema=False)
async def ah_oauth_callback(request: Request, code: str | None = None):
    flow_id = request.cookies.get(_FLOW_COOKIE)
    flow = get_ah_oauth_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=410, detail="AH-login is verlopen. Start de koppeling opnieuw.")
    if not str(code or "").strip():
        raise HTTPException(status_code=400, detail="AH-login gaf geen autorisatiecode terug")

    client = AHReceiptClient()
    try:
        session = client.exchange_code(str(code))
        save_ah_session(engine, flow.household_id, session)
        consume_ah_oauth_flow(flow.flow_id)
        response = RedirectResponse(url=_return_with_status(flow, "connected"), status_code=302)
        response.delete_cookie(_FLOW_COOKIE, path="/")
        return response
    except (httpx.HTTPError, ValueError):
        consume_ah_oauth_flow(flow.flow_id)
        response = RedirectResponse(url=_return_with_status(flow, "error"), status_code=302)
        response.delete_cookie(_FLOW_COOKIE, path="/")
        return response
    finally:
        client.close()


@router.api_route(
    "/{path:ahproxy}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def proxy_ah_login(path: str, request: Request):
    flow_id = request.cookies.get(_FLOW_COOKIE)
    flow = get_ah_oauth_flow(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Niet gevonden")
    if path.startswith("api/") or path.startswith("ah-oauth/"):
        raise HTTPException(status_code=404, detail="Niet gevonden")

    query = request.url.query
    upstream_url = f"{AH_LOGIN_BASE_URL}/{path}"
    if query:
        upstream_url += f"?{query}"

    headers = build_ah_forward_headers(request, backend_origin=flow.backend_origin)

    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            upstream = await client.request(
                request.method,
                upstream_url,
                headers=headers,
                content=body if body else None,
            )
    except httpx.HTTPError as exc:
        logger.warning(
            "AH OAuth proxy request failed: method=%s path=/%s error=%s",
            request.method,
            path,
            type(exc).__name__,
        )
        raise

    content_type = str(upstream.headers.get("content-type") or "")
    location = str(upstream.headers.get("location") or "")
    location_parsed = urlparse(location) if location else None
    location_summary = ""
    if location_parsed is not None:
        location_summary = f"{location_parsed.scheme}://{location_parsed.netloc}{location_parsed.path}"
    logger.info(
        "AH OAuth proxy response: method=%s path=/%s status=%s content_type=%s location=%s",
        request.method,
        path,
        upstream.status_code,
        content_type.split(";", 1)[0],
        location_summary,
    )
    payload = upstream.content
    if any(marker in content_type.lower() for marker in ("text/html", "javascript", "json")):
        payload = rewrite_ah_oauth_body(payload, backend_origin=flow.backend_origin)

    response = Response(content=payload, status_code=upstream.status_code)
    excluded = {
        "content-length",
        "content-encoding",
        "transfer-encoding",
        "connection",
        "set-cookie",
        "location",
        "content-security-policy",
        "strict-transport-security",
        "x-frame-options",
    }
    for name, value in upstream.headers.items():
        if name.lower() not in excluded:
            response.headers[name] = value

    location = upstream.headers.get("location")
    if location:
        response.headers["location"] = _rewrite_location(location, backend_origin=flow.backend_origin)

    for set_cookie in upstream.headers.get_list("set-cookie"):
        sanitized = sanitize_ah_set_cookie(set_cookie)
        if sanitized:
            response.headers.append("set-cookie", sanitized)

    return response


def reset_ah_oauth_flows_for_tests() -> None:
    with _flow_lock:
        _flows.clear()
