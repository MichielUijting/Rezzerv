from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar


API_URL = os.getenv("REZZERV_TEST_API_URL", "http://127.0.0.1:8000").rstrip("/")
SUPERUSER_EMAIL = os.getenv("REZZERV_TEST_SUPERUSER_EMAIL", "supergebruiker@rezzerv.local")
SUPERUSER_PASSWORD = os.getenv("REZZERV_TEST_SUPERUSER_PASSWORD")
MEMBER_EMAIL = os.getenv("REZZERV_TEST_MEMBER_EMAIL", "lid@rezzerv.local")
MEMBER_PASSWORD = os.getenv("REZZERV_TEST_MEMBER_PASSWORD")
EXPECTED_HOUSEHOLD_ID = os.getenv("REZZERV_TEST_HOUSEHOLD_ID", "0")


@dataclass
class ApiResponse:
    status: int
    payload: object | None


def require_secret(value: str | None, name: str) -> str:
    if not value:
        raise RuntimeError(f"{name} ontbreekt in de testomgeving")
    return value


def opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def request_json(
    client: urllib.request.OpenerDirector,
    method: str,
    path: str,
    payload: dict | None = None,
) -> ApiResponse:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{API_URL}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with client.open(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return ApiResponse(response.status, json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return ApiResponse(error.code, parsed)


def login(email: str, password: str) -> tuple[urllib.request.OpenerDirector, dict]:
    client = opener()
    response = request_json(
        client,
        "POST",
        "/api/auth/login",
        {"email": email, "password": password},
    )
    assert response.status == 200, f"Login {email} gaf {response.status}: {response.payload}"
    assert isinstance(response.payload, dict), f"Loginpayload {email} is ongeldig"
    return client, response.payload


def assert_household_context(payload: dict, expected_role: str) -> None:
    assert str(payload.get("active_household_id")) == EXPECTED_HOUSEHOLD_ID, payload
    assert str(payload.get("role") or "").lower() == expected_role, payload


def main() -> int:
    superuser_password = require_secret(SUPERUSER_PASSWORD, "REZZERV_TEST_SUPERUSER_PASSWORD")
    member_password = require_secret(MEMBER_PASSWORD, "REZZERV_TEST_MEMBER_PASSWORD")

    superuser_client, superuser_login = login(SUPERUSER_EMAIL, superuser_password)
    assert_household_context(superuser_login, "owner")

    superuser_session = request_json(superuser_client, "GET", "/api/session")
    assert superuser_session.status == 200, superuser_session
    assert_household_context(superuser_session.payload, "owner")

    superuser_household = request_json(superuser_client, "GET", "/api/household")
    assert superuser_household.status == 200, superuser_household

    superuser_platform = request_json(
        superuser_client,
        "GET",
        "/api/platform/support/threads?status=Open",
    )
    assert superuser_platform.status == 200, superuser_platform

    member_client, member_login = login(MEMBER_EMAIL, member_password)
    assert_household_context(member_login, "member")

    member_session = request_json(member_client, "GET", "/api/session")
    assert member_session.status == 200, member_session
    assert_household_context(member_session.payload, "member")

    member_household = request_json(member_client, "GET", "/api/household")
    assert member_household.status == 200, member_household

    member_platform = request_json(
        member_client,
        "GET",
        "/api/platform/support/threads?status=Open",
    )
    assert member_platform.status == 403, member_platform

    print("authorization_role_matrix: PASS")
    print(f"superuser={SUPERUSER_EMAIL}; household={EXPECTED_HOUSEHOLD_ID}; role=owner")
    print(f"member={MEMBER_EMAIL}; household={EXPECTED_HOUSEHOLD_ID}; role=member")
    print("member_platform_access=403")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"authorization_role_matrix: FAIL: {exc}", file=sys.stderr)
        raise
