"""Compatibility adapter between the existing Rezzerv auth profile and the
central household context policy.

The adapter deliberately separates authentication data from authorization data:
- ``principal`` comes from the validated login/session/token;
- ``membership_rows`` come from the server-side household membership store;
- ``requested_household_id`` may select, but never grant, access.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from app.services.household_context_service import (
    HouseholdContext,
    resolve_household_context,
)


def principal_from_legacy_auth_profile(
    *,
    email: str | None,
    profile: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Translate the current runtime auth profile to a neutral principal.

    This function does not treat the profile's household fields as membership
    proof. They are only the preferred active-household selection. Membership
    proof must still be supplied separately through ``membership_rows``.
    """

    if not profile:
        return None
    normalized_email = str(email or profile.get("email") or "").strip().lower()
    user_id = str(profile.get("user_id") or profile.get("id") or normalized_email).strip()
    return {
        "user_id": user_id,
        "email": normalized_email,
        "active_household_id": str(
            profile.get("active_household_id")
            or profile.get("household_id")
            or ""
        ).strip(),
    }


def membership_rows_from_legacy_auth_profile(
    *,
    email: str | None,
    profile: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build the single verified legacy membership during migration.

    The caller may use this only after the profile was loaded from the trusted
    server-side auth store. Request payloads and client headers are not valid
    inputs for this function.
    """

    if not profile:
        return []
    household_id = str(profile.get("household_id") or "").strip()
    if not household_id:
        return []
    return [
        {
            "household_id": household_id,
            "household_key": str(profile.get("household_key") or "").strip() or None,
            "household_name": str(profile.get("household_name") or "").strip() or None,
            "role": profile.get("role"),
            "user_email": str(email or profile.get("email") or "").strip().lower(),
        }
    ]


def resolve_legacy_household_context(
    *,
    email: str | None,
    profile: Mapping[str, Any] | None,
    requested_household_id: Any = None,
    membership_rows: Iterable[Mapping[str, Any]] | None = None,
) -> HouseholdContext:
    """Resolve central context from the current Rezzerv auth representation.

    ``membership_rows`` should be provided by the database-backed membership
    loader. The single-profile fallback exists only for the current migration
    period and is safe only because ``profile`` is server-side trusted data.
    """

    principal = principal_from_legacy_auth_profile(email=email, profile=profile)
    verified_memberships = list(membership_rows or [])
    if not verified_memberships:
        verified_memberships = membership_rows_from_legacy_auth_profile(
            email=email,
            profile=profile,
        )
    return resolve_household_context(
        principal=principal,
        memberships=verified_memberships,
        requested_household_id=requested_household_id,
    )


def household_context_from_runtime_context(
    runtime_context: Mapping[str, Any] | None,
) -> HouseholdContext:
    """Map the already verified runtime context to the central value object.

    The input must come from ``require_household_context`` or
    ``require_inventory_write_context``. This adapter performs no authentication
    and grants no additional household access.
    """

    if not runtime_context:
        return resolve_household_context(
            principal=None,
            memberships=[],
            requested_household_id=None,
        )

    household_id = str(
        runtime_context.get("active_household_id")
        or runtime_context.get("household_id")
        or ""
    ).strip()

    principal = {
        "user_id": runtime_context.get("user_id") or runtime_context.get("email"),
        "email": runtime_context.get("email"),
        "active_household_id": household_id,
    }
    membership = {
        "household_id": household_id,
        "household_key": runtime_context.get("household_key"),
        "household_name": (
            runtime_context.get("active_household_name")
            or runtime_context.get("household_name")
        ),
        "role": runtime_context.get("role") or runtime_context.get("display_role"),
    }

    return resolve_household_context(
        principal=principal,
        memberships=[membership],
        requested_household_id=household_id,
    )
