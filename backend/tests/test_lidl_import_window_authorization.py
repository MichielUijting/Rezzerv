"""Lidl import window authorization guard contract."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api import retailer_receipt_routes as routes


def test_household_member_cannot_write_without_manage_permission(monkeypatch):
    monkeypatch.setattr(routes, "engine", MagicMock())
    monkeypatch.setattr(
        routes, "_context_and_membership",
        lambda conn: (SimpleNamespace(active_household_id="household-a"), "member-a"),
    )
    monkeypatch.setattr(
        routes, "evaluate_household_permission",
        lambda *args, **kwargs: SimpleNamespace(allowed=False),
    )
    with pytest.raises(HTTPException) as exc:
        routes.update_lidl_import_window(routes.LidlImportWindowRequest(
            from_date="2026-01-01", to_date="2026-01-31"
        ))
    assert exc.value.status_code == 403
    assert "beheerder" in exc.value.detail
