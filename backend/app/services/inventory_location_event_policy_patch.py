from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException

from app.services.inventory_location_policy_service import resolve_inventory_location
from app.services.purchase_import_location_policy_patch import (
    _processing_household_id,
)


def resolve_event_location_for_active_batch(
    resolved_location: dict[str, Any] | None,
    legacy_require_resolved_location: Callable[[dict[str, Any] | None], dict[str, Any]],
) -> dict[str, Any]:
    """Allow a real NULL/NULL event location only inside a policy-bound batch.

    The purchase-import adapter sets ``_processing_household_id`` only after the
    household product configuration has been resolved. Its target resolver already
    rejects supplied locations for ``location_tracking_level='none'`` and never
    returns a NULL/NULL payload for ``global`` or ``exact``. Therefore an all-NULL
    payload that reaches this boundary while the batch context is active is the
    canonical locationless case; every other call keeps the legacy location guard.
    """

    if not resolved_location:
        return legacy_require_resolved_location(resolved_location)

    household_id = _processing_household_id.get()
    has_explicit_location = bool(
        resolved_location.get("space_id") or resolved_location.get("sublocation_id")
    )
    if household_id and not has_explicit_location:
        return resolved_location
    return legacy_require_resolved_location(resolved_location)


def _canonical_event_location(
    conn,
    household_id: str,
    resolved_location: dict[str, Any] | None,
) -> dict[str, Any]:
    candidate = dict(resolved_location or {})
    return resolve_inventory_location(
        conn,
        household_id,
        space_id=candidate.get("space_id"),
        sublocation_id=candidate.get("sublocation_id"),
    )


def install_inventory_location_event_policy_patch(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "inventory_location_event_policy_patch_installed", False):
        return

    legacy_require_resolved_location = main_module.require_resolved_location
    legacy_create_inventory_event = main_module.create_inventory_event

    def require_resolved_location_with_household_policy(resolved_location):
        return resolve_event_location_for_active_batch(
            resolved_location,
            legacy_require_resolved_location,
        )

    def create_inventory_event_with_household_policy(
        conn,
        *,
        household_id,
        resolved_location,
        **kwargs,
    ):
        try:
            canonical_location = _canonical_event_location(
                conn,
                str(household_id),
                resolved_location,
            )
        except LookupError:
            # Legacy/test households without canonical product configuration keep
            # the old strict behavior. This is deliberately fail-closed.
            return legacy_create_inventory_event(
                conn,
                household_id=household_id,
                resolved_location=resolved_location,
                **kwargs,
            )
        except HTTPException:
            raise

        is_locationless = not (
            canonical_location.get("space_id")
            or canonical_location.get("sublocation_id")
        )
        if not is_locationless:
            return legacy_create_inventory_event(
                conn,
                household_id=household_id,
                resolved_location=canonical_location,
                **kwargs,
            )

        token = _processing_household_id.set(str(household_id))
        try:
            return legacy_create_inventory_event(
                conn,
                household_id=household_id,
                resolved_location=canonical_location,
                **kwargs,
            )
        finally:
            _processing_household_id.reset(token)

    main_module.require_resolved_location = (
        require_resolved_location_with_household_policy
    )
    main_module.create_inventory_event = create_inventory_event_with_household_policy
    app.state.inventory_location_event_policy_patch_installed = True
