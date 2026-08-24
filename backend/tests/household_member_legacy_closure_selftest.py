"""Self-contained validation for Onboarding v2 I.4 legacy member-create closure."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.legacy_household_member_creation_closure import (
    LEGACY_MEMBER_CREATE_PATH,
    REPLACEMENT_INVITATION_PATH,
    create_legacy_household_member_creation_closure_router,
    retire_legacy_household_member_create_route,
)


def run() -> int:
    checks: list[str] = []
    calls = {"legacy_create": 0, "get": 0, "put": 0, "delete": 0}
    app = FastAPI()

    @app.get(LEGACY_MEMBER_CREATE_PATH)
    def get_household_members():
        calls["get"] += 1
        return {"ok": True, "method": "GET"}

    @app.post(LEGACY_MEMBER_CREATE_PATH)
    def create_household_member(payload: dict | None = None):
        calls["legacy_create"] += 1
        return {"danger": "legacy mutation executed", "payload": payload}

    @app.put("/api/household/members/{member_email}")
    def update_household_member(member_email: str):
        calls["put"] += 1
        return {"ok": True, "method": "PUT", "email": member_email}

    @app.delete("/api/household/members/{member_email}")
    def delete_household_member(member_email: str):
        calls["delete"] += 1
        return {"ok": True, "method": "DELETE", "email": member_email}

    retired = retire_legacy_household_member_create_route(app)
    assert retired.path == LEGACY_MEMBER_CREATE_PATH
    assert "POST" in retired.methods
    assert retired.endpoint.__name__ == "create_household_member"
    checks.append("exact_legacy_post_is_retired")

    app.include_router(create_legacy_household_member_creation_closure_router())

    with TestClient(app) as client:
        get_response = client.get(LEGACY_MEMBER_CREATE_PATH)
        assert get_response.status_code == 200, get_response.text
        assert get_response.json()["method"] == "GET"

        put_response = client.put("/api/household/members/lid@example.com")
        assert put_response.status_code == 200, put_response.text
        assert put_response.json()["method"] == "PUT"

        delete_response = client.delete("/api/household/members/lid@example.com")
        assert delete_response.status_code == 200, delete_response.text
        assert delete_response.json()["method"] == "DELETE"
    assert calls["get"] == 1
    assert calls["put"] == 1
    assert calls["delete"] == 1
    checks.append("get_put_delete_member_management_remains_available")

    with TestClient(app) as client:
        post_response = client.post(
            LEGACY_MEMBER_CREATE_PATH,
            json={
                "email": "candidate@example.com",
                "password": "NeverCreateThisAccount",
                "role": "admin",
            },
        )
    assert post_response.status_code == 410, post_response.text
    detail = post_response.json()["detail"]
    assert detail["code"] == "legacy_household_member_creation_retired"
    assert detail["replacement"] == REPLACEMENT_INVITATION_PATH
    assert calls["legacy_create"] == 0
    checks.append("legacy_post_returns_410_without_executing_mutation")

    try:
        retire_legacy_household_member_create_route(app)
    except RuntimeError as exc:
        assert "found 0" in str(exc)
    else:
        raise AssertionError("legacy closure unexpectedly allowed a second retirement pass")
    checks.append("closure_fails_loudly_if_expected_legacy_route_is_absent")

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("HOUSEHOLD_MEMBER_LEGACY_CLOSURE_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
