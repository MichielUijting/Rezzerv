from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from sqlalchemy import text

from app.db import engine
from app.services.authorization_foundation_service import ensure_authorization_foundation


API_URL = os.getenv("REZZERV_TEST_API_URL", "http://127.0.0.1:8000").rstrip("/")
SUPERUSER_EMAIL = os.getenv("REZZERV_TEST_SUPERUSER_EMAIL", "supergebruiker@rezzerv.local")
SUPERUSER_PASSWORD = os.getenv("REZZERV_TEST_SUPERUSER_PASSWORD")
OWNER_EMAIL = os.getenv("REZZERV_TEST_OWNER_EMAIL", "regressie-eigenaar@rezzerv.local")
OWNER_PASSWORD = os.getenv("REZZERV_TEST_OWNER_PASSWORD")
MEMBER_EMAIL = os.getenv("REZZERV_TEST_MEMBER_EMAIL", "regressie-lid@rezzerv.local")
MEMBER_PASSWORD = os.getenv("REZZERV_TEST_MEMBER_PASSWORD")
REGRESSION_HOUSEHOLD_ID = os.getenv("REZZERV_TEST_HOUSEHOLD_ID", "1")


@dataclass
class ApiResponse:
    status: int
    payload: object | None


def require_secret(value: str | None, name: str) -> str:
    if not value:
        raise RuntimeError(f"{name} ontbreekt in de testomgeving")
    return value


def provision_role_fixture(*, email: str, password: str, legacy_role: str, role_key: str) -> None:
    user_id = email
    membership_id = f"fixture-{role_key.replace('.', '-')}-{REGRESSION_HOUSEHOLD_ID}"
    with engine.begin() as connection:
        ensure_authorization_foundation(connection)
        connection.execute(
            text(
                """
                INSERT INTO app_users (id, email, password, created_at, updated_at)
                VALUES (:id, :email, :password, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(email) DO UPDATE SET
                    password = excluded.password,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"id": user_id, "email": email, "password": password},
        )
        existing_membership = connection.execute(
            text(
                """
                SELECT id
                FROM household_memberships
                WHERE CAST(household_id AS TEXT) = :household_id
                  AND lower(user_email) = lower(:email)
                LIMIT 1
                """
            ),
            {"household_id": REGRESSION_HOUSEHOLD_ID, "email": email},
        ).scalar()
        if existing_membership:
            membership_id = str(existing_membership)
            connection.execute(
                text(
                    """
                    UPDATE household_memberships
                    SET role = :legacy_role,
                        status = 'active',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :membership_id
                    """
                ),
                {"membership_id": membership_id, "legacy_role": legacy_role},
            )
        else:
            connection.execute(
                text(
                    """
                    INSERT INTO household_memberships
                        (id, household_id, user_email, role, status, created_at, updated_at)
                    VALUES
                        (:id, :household_id, :email, :legacy_role, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "id": membership_id,
                    "household_id": REGRESSION_HOUSEHOLD_ID,
                    "email": email,
                    "legacy_role": legacy_role,
                },
            )
        connection.execute(
            text(
                """
                INSERT INTO auth_membership_roles
                    (household_id, membership_id, role_key, active, created_at, updated_at)
                VALUES
                    (:household_id, :membership_id, :role_key, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(household_id, membership_id) DO UPDATE SET
                    role_key = excluded.role_key,
                    active = 1,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "household_id": REGRESSION_HOUSEHOLD_ID,
                "membership_id": membership_id,
                "role_key": role_key,
            },
        )
    print(
        "authorization_fixture: PASS; "
        f"email={email}; household={REGRESSION_HOUSEHOLD_ID}; role={role_key}"
    )


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


def assert_household_context(payload: dict, *, household_id: str, role: str) -> None:
    assert str(payload.get("active_household_id")) == household_id, payload
    assert str(payload.get("role") or "").lower() == role, payload


def assert_platform_access(client: urllib.request.OpenerDirector, expected_status: int) -> None:
    response = request_json(client, "GET", "/api/platform/support/threads?status=Open")
    assert response.status == expected_status, response


def main() -> int:
    superuser_password = require_secret(SUPERUSER_PASSWORD, "REZZERV_TEST_SUPERUSER_PASSWORD")
    owner_password = require_secret(OWNER_PASSWORD, "REZZERV_TEST_OWNER_PASSWORD")
    member_password = require_secret(MEMBER_PASSWORD, "REZZERV_TEST_MEMBER_PASSWORD")

    provision_role_fixture(
        email=OWNER_EMAIL,
        password=owner_password,
        legacy_role="owner",
        role_key="household.owner",
    )
    provision_role_fixture(
        email=MEMBER_EMAIL,
        password=member_password,
        legacy_role="member",
        role_key="household.member",
    )

    superuser_client, superuser_login = login(SUPERUSER_EMAIL, superuser_password)
    assert_household_context(superuser_login, household_id="0", role="owner")
    assert_platform_access(superuser_client, 200)

    owner_client, owner_login = login(OWNER_EMAIL, owner_password)
    assert_household_context(owner_login, household_id=REGRESSION_HOUSEHOLD_ID, role="owner")
    assert request_json(owner_client, "GET", "/api/household").status == 200
    assert_platform_access(owner_client, 403)

    member_client, member_login = login(MEMBER_EMAIL, member_password)
    assert_household_context(member_login, household_id=REGRESSION_HOUSEHOLD_ID, role="member")
    assert request_json(member_client, "GET", "/api/household").status == 200
    assert_platform_access(member_client, 403)

    print("authorization_role_matrix: PASS")
    print(f"superuser={SUPERUSER_EMAIL}; household=0; role=owner; platform=200")
    print(
        f"owner={OWNER_EMAIL}; household={REGRESSION_HOUSEHOLD_ID}; "
        "role=owner; platform=403"
    )
    print(
        f"member={MEMBER_EMAIL}; household={REGRESSION_HOUSEHOLD_ID}; "
        "role=member; platform=403"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"authorization_role_matrix: FAIL: {exc}", file=sys.stderr)
        raise
