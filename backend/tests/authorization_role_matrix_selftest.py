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

from sqlalchemy import inspect, text

from app.db import engine
from app.services.authorization_foundation_service import ensure_authorization_foundation

API_URL = os.getenv("REZZERV_TEST_API_URL", "http://127.0.0.1:8000").rstrip("/")
SUPERUSER_EMAIL = os.getenv("REZZERV_TEST_SUPERUSER_EMAIL", "supergebruiker@rezzerv.local")
SUPERUSER_PASSWORD = os.getenv("REZZERV_TEST_SUPERUSER_PASSWORD")
TEST_ADMIN_EMAIL = os.getenv("REZZERV_TEST_ADMIN_EMAIL", "test-admin@rezzerv.local")
TEST_ADMIN_PASSWORD = os.getenv("REZZERV_TEST_ADMIN_PASSWORD")
HOUSEHOLD_ID = "0"


@dataclass
class ApiResponse:
    status: int
    payload: object | None


def require_secret(value: str | None, name: str) -> str:
    if not value:
        raise RuntimeError(f"{name} ontbreekt in de testomgeving")
    return value


def table_columns(connection, table_name: str) -> set[str]:
    inspector = inspect(connection)
    return {
        str(column.get("name") or "")
        for column in inspector.get_columns(table_name)
    }


def provision_test_admin(password: str) -> None:
    membership_id = "fixture-test-admin-household-0"
    with engine.begin() as connection:
        ensure_authorization_foundation(connection)
        connection.execute(
            text(
                """
                INSERT INTO household_registry (id, naam, created_at)
                VALUES ('0', 'Regressietest huishouden 0', CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET naam = excluded.naam
                """
            )
        )
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
            {"id": TEST_ADMIN_EMAIL, "email": TEST_ADMIN_EMAIL, "password": password},
        )

        membership_columns = table_columns(connection, "household_memberships")
        email_column = "user_email" if "user_email" in membership_columns else "email"
        if email_column not in membership_columns:
            raise RuntimeError("household_memberships heeft geen e-mailkolom")

        connection.execute(
            text(
                f"DELETE FROM household_memberships "
                f"WHERE lower({email_column}) = lower(:email)"
            ),
            {"email": TEST_ADMIN_EMAIL},
        )

        insert_columns = ["id", "household_id", email_column, "role"]
        insert_values = [":id", "'0'", ":email", "'owner'"]
        if "status" in membership_columns:
            insert_columns.append("status")
            insert_values.append("'active'")
        if "created_at" in membership_columns:
            insert_columns.append("created_at")
            insert_values.append("CURRENT_TIMESTAMP")
        if "updated_at" in membership_columns:
            insert_columns.append("updated_at")
            insert_values.append("CURRENT_TIMESTAMP")

        connection.execute(
            text(
                f"INSERT INTO household_memberships ({', '.join(insert_columns)}) "
                f"VALUES ({', '.join(insert_values)})"
            ),
            {"id": membership_id, "email": TEST_ADMIN_EMAIL},
        )
        connection.execute(
            text(
                """
                INSERT INTO auth_membership_roles
                    (household_id, membership_id, role_key, active, created_at, updated_at)
                VALUES
                    ('0', :membership_id, 'household.owner', TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(household_id, membership_id) DO UPDATE SET
                    role_key = 'household.owner',
                    active = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"membership_id": membership_id},
        )

    print(
        "authorization_fixture: PASS; "
        f"email={TEST_ADMIN_EMAIL}; household=0; role=household.owner"
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


def assert_household_zero(payload: dict, expected_email: str) -> None:
    assert str(payload.get("active_household_id")) == HOUSEHOLD_ID, payload
    assert str(payload.get("role") or "").lower() == "owner", payload
    assert str(payload.get("email") or "").lower() == expected_email.lower(), payload


def main() -> int:
    if str(os.getenv("REZZERV_PROVISION_TEST_HOUSEHOLD_ZERO", "false")).lower() not in {
        "1", "true", "yes", "on"
    }:
        raise RuntimeError("REZZERV_PROVISION_TEST_HOUSEHOLD_ZERO moet true zijn")

    superuser_password = require_secret(SUPERUSER_PASSWORD, "REZZERV_TEST_SUPERUSER_PASSWORD")
    test_admin_password = require_secret(TEST_ADMIN_PASSWORD, "REZZERV_TEST_ADMIN_PASSWORD")
    provision_test_admin(test_admin_password)

    superuser_client, superuser_login = login(SUPERUSER_EMAIL, superuser_password)
    assert_household_zero(superuser_login, SUPERUSER_EMAIL)
    superuser_platform = request_json(
        superuser_client,
        "GET",
        "/api/platform/support/threads?status=Open",
    )
    assert superuser_platform.status == 200, superuser_platform

    test_admin_client, test_admin_login = login(TEST_ADMIN_EMAIL, test_admin_password)
    assert_household_zero(test_admin_login, TEST_ADMIN_EMAIL)
    household = request_json(test_admin_client, "GET", "/api/household")
    assert household.status == 200, household
    memberships = household.payload.get("memberships") if isinstance(household.payload, dict) else None
    if memberships is not None:
        assert len(memberships) == 1, household.payload
        assert str(memberships[0].get("household_id")) == "0", household.payload

    test_admin_platform = request_json(
        test_admin_client,
        "GET",
        "/api/platform/support/threads?status=Open",
    )
    assert test_admin_platform.status == 403, test_admin_platform

    test_admin_external_databases = request_json(
        test_admin_client,
        "GET",
        "/api/external-databases/summary",
    )
    assert test_admin_external_databases.status == 403, test_admin_external_databases

    print("authorization_role_matrix: PASS")
    print(f"superuser={SUPERUSER_EMAIL}; household=0; role=owner; platform=200")
    print(f"test_admin={TEST_ADMIN_EMAIL}; household=0; role=owner; platform=403")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"authorization_role_matrix: FAIL: {exc}", file=sys.stderr)
        raise
