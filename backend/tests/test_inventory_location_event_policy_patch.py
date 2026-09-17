import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from app.services import inventory_location_event_policy_patch as policy_patch
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


def _locationless_payload():
    return {
        "location_id": None,
        "space_id": None,
        "sublocation_id": None,
        "location_label": "",
    }


def _location_payload():
    return {
        "location_id": "space-1",
        "space_id": "space-1",
        "sublocation_id": None,
        "location_label": "Keuken",
    }


def _fake_main_module():
    module = SimpleNamespace()
    module.app = SimpleNamespace(state=SimpleNamespace())

    def require_resolved_location(resolved_location):
        candidate = resolved_location or {}
        if not (candidate.get("space_id") or candidate.get("sublocation_id")):
            raise HTTPException(
                status_code=400,
                detail="Voorraadmutatie vereist een expliciete ruimte of sublocatie",
            )
        return candidate

    def create_inventory_event(
        conn,
        *,
        household_id,
        resolved_location,
        **kwargs,
    ):
        safe_location = module.require_resolved_location(resolved_location)
        return {
            "household_id": household_id,
            "resolved_location": safe_location,
            "kwargs": kwargs,
        }

    def build_location_payload_from_inventory_row(inventory_row):
        space_id = inventory_row.get("space_id")
        sublocation_id = inventory_row.get("sublocation_id")
        return {
            "location_id": sublocation_id or space_id,
            "space_id": space_id,
            "sublocation_id": sublocation_id,
            "location_label": inventory_row.get("location_label") or "",
        }

    module.require_resolved_location = require_resolved_location
    module.create_inventory_event = create_inventory_event
    module.build_location_payload_from_inventory_row = (
        build_location_payload_from_inventory_row
    )
    return module


def test_locationless_event_payload_is_allowed_only_inside_active_batch_context():
    locationless = _locationless_payload()

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
    exact = _location_payload()
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


def test_manual_inventory_event_allows_null_location_when_household_locations_are_off(monkeypatch):
    module = _fake_main_module()
    monkeypatch.setattr(
        policy_patch,
        "resolve_inventory_location",
        lambda conn, household_id, **kwargs: _locationless_payload(),
    )

    policy_patch.install_inventory_location_event_policy_patch(module)

    result = module.create_inventory_event(
        object(),
        household_id="household-none",
        resolved_location=_locationless_payload(),
        event_type="consume",
        quantity=-1,
    )

    assert result["resolved_location"] == _locationless_payload()
    assert policy_patch._processing_household_id.get() is None


@pytest.mark.parametrize("event_type", ["consume", "manual_adjustment"])
def test_existing_inventory_row_ignores_historical_location_when_household_is_locationless(
    monkeypatch,
    event_type,
):
    module = _fake_main_module()
    resolver_calls = []

    monkeypatch.setattr(
        policy_patch,
        "resolve_household_product_configuration",
        lambda conn, household_id: SimpleNamespace(location_tracking_level="none"),
    )

    def strict_locationless_resolver(conn, household_id, **kwargs):
        resolver_calls.append(dict(kwargs))
        if kwargs.get("space_id") or kwargs.get("sublocation_id"):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Dit huishouden gebruikt voorraad zonder locatie; "
                    "space_id en sublocation_id zijn niet toegestaan"
                ),
            )
        return _locationless_payload()

    monkeypatch.setattr(
        policy_patch,
        "resolve_inventory_location",
        strict_locationless_resolver,
    )
    policy_patch.install_inventory_location_event_policy_patch(module)

    persisted_location = module.build_location_payload_from_inventory_row(
        {
            "space_id": "historical-space",
            "sublocation_id": None,
            "location_label": "Oude locatie",
        }
    )
    result = module.create_inventory_event(
        object(),
        household_id="household-none",
        resolved_location=persisted_location,
        event_type=event_type,
        source="manual_inventory_api",
        quantity=-1 if event_type == "consume" else 1,
    )

    assert result["resolved_location"] == _locationless_payload()
    assert resolver_calls == [{}]
    assert policy_patch._processing_household_id.get() is None


def test_locationless_household_still_rejects_new_explicit_location_input(monkeypatch):
    module = _fake_main_module()

    def reject_explicit_location(conn, household_id, **kwargs):
        if kwargs.get("space_id") or kwargs.get("sublocation_id"):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Dit huishouden gebruikt voorraad zonder locatie; "
                    "space_id en sublocation_id zijn niet toegestaan"
                ),
            )
        return _locationless_payload()

    monkeypatch.setattr(
        policy_patch,
        "resolve_inventory_location",
        reject_explicit_location,
    )
    policy_patch.install_inventory_location_event_policy_patch(module)

    with pytest.raises(HTTPException) as exc_info:
        module.create_inventory_event(
            object(),
            household_id="household-none",
            resolved_location=_location_payload(),
            event_type="consume",
            source="manual_inventory_api",
            quantity=-1,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "Dit huishouden gebruikt voorraad zonder locatie; "
        "space_id en sublocation_id zijn niet toegestaan"
    )


def test_manual_inventory_event_keeps_locations_required_when_policy_requires_them(monkeypatch):
    module = _fake_main_module()

    def reject_missing_location(conn, household_id, **kwargs):
        raise HTTPException(
            status_code=400,
            detail="Een hoofdruimte is verplicht voor dit huishouden",
        )

    monkeypatch.setattr(policy_patch, "resolve_inventory_location", reject_missing_location)
    policy_patch.install_inventory_location_event_policy_patch(module)

    with pytest.raises(HTTPException) as exc_info:
        module.create_inventory_event(
            object(),
            household_id="household-global",
            resolved_location=_locationless_payload(),
            event_type="consume",
            quantity=-1,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Een hoofdruimte is verplicht voor dit huishouden"


def test_manual_inventory_event_uses_canonical_valid_location(monkeypatch):
    module = _fake_main_module()
    monkeypatch.setattr(
        policy_patch,
        "resolve_inventory_location",
        lambda conn, household_id, **kwargs: _location_payload(),
    )
    policy_patch.install_inventory_location_event_policy_patch(module)

    result = module.create_inventory_event(
        object(),
        household_id="household-global",
        resolved_location=_location_payload(),
        event_type="consume",
        quantity=-1,
    )

    assert result["resolved_location"] == _location_payload()


def test_household_without_product_configuration_keeps_legacy_strict_guard(monkeypatch):
    module = _fake_main_module()

    def missing_configuration(conn, household_id, **kwargs):
        raise LookupError("Geen productconfiguratie")

    monkeypatch.setattr(policy_patch, "resolve_inventory_location", missing_configuration)
    policy_patch.install_inventory_location_event_policy_patch(module)

    with pytest.raises(HTTPException) as exc_info:
        module.create_inventory_event(
            object(),
            household_id="legacy-household",
            resolved_location=_locationless_payload(),
            event_type="consume",
            quantity=-1,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "Voorraadmutatie vereist een expliciete ruimte of sublocatie"
    )
