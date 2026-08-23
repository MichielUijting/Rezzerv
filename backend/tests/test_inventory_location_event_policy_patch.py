import pytest
from fastapi import HTTPException

from app.services.inventory_location_event_policy_patch import (
    resolve_event_location_for_active_batch,
)
from app.services.purchase_import_location_policy_patch import (
    _processing_household_id,
)


def _legacy_guard(resolved_location):
    if not resolved_location:
        raise HTTPException(status_code=400, detail="missing")
    if not resolved_location.get("space_id") and not resolved_location.get("sublocation_id"):
        raise HTTPException(status_code=400, detail="explicit location required")
    return resolved_location


def test_locationless_event_payload_is_allowed_only_inside_active_batch_context():
    locationless = {
        "location_id": None,
        "space_id": None,
        "sublocation_id": None,
        "location_label": "",
    }

    with pytest.raises(HTTPException):
        resolve_event_location_for_active_batch(locationless, _legacy_guard)

    token = _processing_household_id.set("house-none")
    try:
        assert (
            resolve_event_location_for_active_batch(locationless, _legacy_guard)
            is locationless
        )
    finally:
        _processing_household_id.reset(token)


def test_explicit_location_keeps_legacy_guard_even_inside_batch_context():
    exact = {
        "location_id": "space-1",
        "space_id": "space-1",
        "sublocation_id": None,
        "location_label": "Keuken",
    }
    token = _processing_household_id.set("house-exact")
    try:
        assert resolve_event_location_for_active_batch(exact, _legacy_guard) is exact
    finally:
        _processing_household_id.reset(token)


def test_missing_location_payload_is_never_accepted():
    token = _processing_household_id.set("house-none")
    try:
        with pytest.raises(HTTPException):
            resolve_event_location_for_active_batch(None, _legacy_guard)
    finally:
        _processing_household_id.reset(token)
