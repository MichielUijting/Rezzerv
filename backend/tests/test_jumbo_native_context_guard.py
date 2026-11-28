"""Fail-closed identity and household binding for native/browser Jumbo writes."""
import pytest
from fastapi import HTTPException

from app.api.retailer_receipt_routes import _check_expected_retailer_context


def test_jumbo_same_user_and_household_is_accepted():
    runtime = {"user_id": "test-user", "active_household_id": "household-1"}
    assert _check_expected_retailer_context(runtime, "test-user", "household-1") == "household-1"


@pytest.mark.parametrize("user,household", [
    ("other-user", "household-1"),
    ("test-user", "household-2"),
    (None, "household-1"),
    ("test-user", None),
    ("", ""),
])
def test_jumbo_changed_or_incomplete_context_fails_closed(user, household):
    with pytest.raises(HTTPException) as exc:
        _check_expected_retailer_context(
            {"user_id": "test-user", "active_household_id": "household-1"}, user, household,
        )
    assert exc.value.status_code == 409


def test_legacy_no_context_headers_does_not_override_backend_authority():
    with pytest.raises(HTTPException) as exc:
        _check_expected_retailer_context(
            {"user_id": "test-user", "active_household_id": "household-1"}, "test-user", "household-2",
        )
    assert exc.value.status_code == 409
