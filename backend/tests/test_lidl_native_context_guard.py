"""Native Lidl requires the same authoritative user+household on every write."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import retailer_receipt_routes as routes


def test_native_lidl_begin_requires_exact_backend_context(monkeypatch):
    seen = {}
    def check(auth, user, household):
        seen["args"] = (auth, user, household)
        if user != "correct-user" or household != "correct-household":
            raise HTTPException(status_code=409, detail="session changed")
        return household
    monkeypatch.setattr(routes, "_import_bound_household_id", check)
    monkeypatch.setattr(routes, "begin_lidl_browser_import", lambda engine, household: {"household": household})
    result = routes.begin_lidl_browser_history(
        authorization="session",
        x_inhuis_expected_user="correct-user",
        x_inhuis_expected_household="correct-household",
    )
    assert result == {"household": "correct-household"}
    assert seen["args"] == ("session", "correct-user", "correct-household")
    with pytest.raises(HTTPException) as exc:
        routes.begin_lidl_browser_history(
            authorization="session",
            x_inhuis_expected_user="other-user",
            x_inhuis_expected_household="correct-household",
        )
    assert exc.value.status_code == 409


def test_native_lidl_complete_cannot_cross_context(monkeypatch):
    def check(auth, user, household):
        if user != "correct-user" or household != "correct-household":
            raise HTTPException(status_code=409, detail="session changed")
        return household
    seen = {}
    def complete(engine, household, **kw):
        seen["household"] = household
        seen["params"] = kw
        return {"scan_complete": True, "staged_receipts": 0}
    monkeypatch.setattr(routes, "_import_bound_household_id", check)
    monkeypatch.setattr(routes, "complete_lidl_browser_import", complete)
    payload = routes.LidlBrowserCompleteRequest(
        run_id="00000000-0000-4000-8000-000000000000",
        queue_ids=[], from_date="2025-01-01", to_date="2026-11-27",
    )
    with pytest.raises(HTTPException) as exc:
        routes.complete_lidl_browser_history(
            payload, authorization="session",
            x_inhuis_expected_user="old-user",
            x_inhuis_expected_household="correct-household",
        )
    assert exc.value.status_code == 409
    assert not seen
    result = routes.complete_lidl_browser_history(
        payload, authorization="session",
        x_inhuis_expected_user="correct-user",
        x_inhuis_expected_household="correct-household",
    )
    assert result["scan_complete"] is True
    assert seen["household"] == "correct-household"
