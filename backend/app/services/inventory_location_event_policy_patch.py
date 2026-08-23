from __future__ import annotations

from typing import Any, Callable

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


def install_inventory_location_event_policy_patch(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "inventory_location_event_policy_patch_installed", False):
        return

    legacy_require_resolved_location = main_module.require_resolved_location

    def require_resolved_location_with_household_policy(resolved_location):
        return resolve_event_location_for_active_batch(
            resolved_location,
            legacy_require_resolved_location,
        )

    main_module.require_resolved_location = (
        require_resolved_location_with_household_policy
    )
    app.state.inventory_location_event_policy_patch_installed = True
