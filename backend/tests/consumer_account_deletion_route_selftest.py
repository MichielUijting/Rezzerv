"""Route boundary for self-service account deletion, without a destructive database."""
from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

from fastapi import HTTPException, Response

from app.api import consumer_account_routes as routes


def run() -> int:
    checks = []
    endpoints = [
        (r.path, set(r.methods or []))
        for r in routes.router.routes
    ]
    assert sum(p == "/api/account" and "DELETE" in methods for p, methods in endpoints) == 1
    assert sum(p == "/api/account/deletion-preview" and "GET" in methods for p, methods in endpoints) == 1
    checks.append("account_routes_unique")

    original = {
        "resolve_current_server_session": routes.resolve_current_server_session,
        "engine": routes.engine,
        "deletion_preview": routes.deletion_preview,
        "delete_consumer_account": routes.delete_consumer_account,
    }
    captured = []
    try:
        routes.engine = SimpleNamespace(begin=lambda: nullcontext(object()))
        routes.deletion_preview = lambda conn, *, user_id: (
            captured.append(("preview", user_id)) or {"households_to_keep": 1}
        )
        routes.delete_consumer_account = lambda conn, **kwargs: (
            captured.append(("delete", kwargs)) or {"deleted": True}
        )
        routes.resolve_current_server_session = lambda: SimpleNamespace(
            context_type="system", user_id="system-actor"
        )
        try:
            routes.get_account_deletion_preview()
        except HTTPException as exc:
            assert exc.status_code == 403
        else:
            raise AssertionError("system context allowed deleting account")

        routes.resolve_current_server_session = lambda: SimpleNamespace(
            context_type="regular", user_id="real-session-user"
        )
        preview = routes.get_account_deletion_preview()
        assert preview["households_to_keep"] == 1
        assert captured[-1] == ("preview", "real-session-user")
        checks.append("preview_uses_authoritative_cookie_session")

        payload = routes.ConsumerAccountDeleteRequest(
            current_password="CorrectPassword123!",
            confirmation="VERWIJDER MIJN ACCOUNT",
        )
        response = Response()
        result = routes.permanently_delete_my_account(payload, response)
        assert result["deleted"] is True
        assert captured[-1][0] == "delete"
        assert captured[-1][1]["user_id"] == "real-session-user"
        assert captured[-1][1]["current_password"] == "CorrectPassword123!"
        assert "set-cookie" in response.headers
        checks.append("self_delete_has_no_caller_controlled_target_and_expires_cookie")
    finally:
        for key, value in original.items():
            setattr(routes, key, value)

    for check in checks:
        print("PASS", check)
    print("RESULT", len(checks), "/", len(checks), "checks passed")
    print("ACCOUNT_DELETION_ROUTE_CONTRACT_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
