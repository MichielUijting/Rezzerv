"""Allowlisted Picnic NL protocol transport.

Picnic has not published a stable integration API; no session or response logs.
Only exact historical-read and authentication endpoints are permitted.
"""
from __future__ import annotations

from typing import Any
import re

import httpx

from app.integrations.picnic_auth_protocol import PicnicAuthError

PICNIC_API_BASE = "https://storefront-prod.nl.picnicinternational.com/api/15"


class PicnicHttpTransport:
    def __init__(self, client: httpx.Client | None = None):
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=httpx.Timeout(15.0), follow_redirects=False)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def send(self, method: str, path: str, payload: Any, auth_key: str | None = None):
        allowed = (
            (method == "POST" and path in {"/user/login", "/user/2fa/generate", "/user/2fa/verify", "/deliveries/summary"})
            or (method == "GET" and re.fullmatch(r"/deliveries/[A-Za-z0-9_-]{1,180}", path) is not None)
        )
        if not allowed:
            raise PicnicAuthError("Picnic-API-actie niet toegestaan.")
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept-Language": "nl",
            "User-Agent": "okhttp/4.9.0",
        }
        if auth_key:
            headers["x-picnic-auth"] = auth_key
        if path in {"/user/2fa/generate", "/user/2fa/verify"}:
            headers.update({"x-picnic-agent": "30100;1.246.1-15599;", "x-picnic-did": "3C417201548B2E3B"})
        try:
            response = self._client.request(method, PICNIC_API_BASE + path, json=payload if method == "POST" else None, headers=headers)
            response.raise_for_status()
            data = response.json() if response.content else {}
            if not isinstance(data, (dict, list)):
                raise PicnicAuthError("Picnic antwoordde in een onbekend formaat.")
            return data, dict(response.headers)
        except PicnicAuthError:
            raise
        except (httpx.HTTPError, ValueError, TypeError):
            raise PicnicAuthError("Picnic-API is niet beschikbaar of weigerde het verzoek.") from None
