"""Central household authorization context for Rezzerv.

This module contains the tenant-isolation policy only. Authentication adapters may
supply an authenticated principal and its verified household memberships, but
request payloads are never allowed to grant household access.

Global product knowledge (global products, product identities, product types and
external article-product links) is intentionally outside this household context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class HouseholdContextError(ValueError):
    """Base error for invalid or unauthorized household context."""


class HouseholdAuthenticationRequired(HouseholdContextError):
    """Raised when no authenticated principal is available."""


class HouseholdMembershipRequired(HouseholdContextError):
    """Raised when the principal has no verified household membership."""


class HouseholdAccessDenied(HouseholdContextError):
    """Raised when a requested household is not among verified memberships."""


@dataclass(frozen=True, slots=True)
class HouseholdContext:
    """Verified server-side context for one household-scoped operation."""

    user_id: str
    email: str
    active_household_id: str
    household_key: str | None
    household_name: str | None
    role: str
    display_role: str

    def as_dict(self) -> dict[str, str | None]:
        """Compatibility representation for existing route code."""

        return {
            "user_id": self.user_id,
            "email": self.email,
            "active_household_id": self.active_household_id,
            "household_key": self.household_key,
            "household_name": self.household_name,
            "role": self.role,
            "display_role": self.display_role,
        }


def normalize_household_role(value: Any) -> str:
    """Normalize legacy and user-facing role names to the domain roles."""

    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {"admin", "owner", "eigenaar", "beheerder"}:
        return "owner"
    if normalized in {"member", "lid"}:
        return "member"
    if normalized in {"viewer", "gast", "read_only", "readonly", "kijker"}:
        return "viewer"
    raise HouseholdAccessDenied("Onbekende of ongeldige huishoudrol")


def display_household_role(role: str) -> str:
    normalized = normalize_household_role(role)
    return {
        "owner": "admin",
        "member": "lid",
        "viewer": "kijker",
    }[normalized]


def _normalized_identifier(value: Any) -> str:
    return str(value or "").strip()


def _membership_household_id(membership: Mapping[str, Any]) -> str:
    return _normalized_identifier(
        membership.get("household_id")
        or membership.get("active_household_id")
        or membership.get("id")
    )


def _membership_index(
    memberships: Iterable[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for membership in memberships:
        household_id = _membership_household_id(membership)
        if household_id:
            indexed[household_id] = membership
    return indexed


def resolve_household_context(
    *,
    principal: Mapping[str, Any] | None,
    memberships: Iterable[Mapping[str, Any]],
    requested_household_id: Any = None,
) -> HouseholdContext:
    """Resolve one authorized household context.

    Security rules:
    - the principal must already be authenticated by a server-side adapter;
    - memberships must be verified server-side, never accepted from a payload;
    - a requested household can only select one of those verified memberships;
    - when no household is requested, the authenticated principal's active
      household is used, with a single-membership fallback for legacy sessions;
    - a payload value can never create or broaden access.
    """

    if not principal:
        raise HouseholdAuthenticationRequired("Authenticatie is verplicht")

    user_id = _normalized_identifier(principal.get("user_id") or principal.get("id"))
    email = _normalized_identifier(principal.get("email")).lower()
    if not user_id and not email:
        raise HouseholdAuthenticationRequired("Geauthenticeerde gebruiker ontbreekt")

    indexed_memberships = _membership_index(memberships)
    if not indexed_memberships:
        raise HouseholdMembershipRequired("Gebruiker is niet gekoppeld aan een huishouden")

    requested = _normalized_identifier(requested_household_id)
    principal_household_id = _normalized_identifier(
        principal.get("active_household_id")
        or principal.get("household_id")
    )

    if requested:
        selected_household_id = requested
    elif principal_household_id:
        selected_household_id = principal_household_id
    elif len(indexed_memberships) == 1:
        selected_household_id = next(iter(indexed_memberships))
    else:
        raise HouseholdAccessDenied("Actief huishouden ontbreekt")

    membership = indexed_memberships.get(selected_household_id)
    if membership is None:
        raise HouseholdAccessDenied("Geen toegang tot het gevraagde huishouden")

    role = normalize_household_role(membership.get("role") or principal.get("role"))
    household_key = _normalized_identifier(
        membership.get("household_key") or principal.get("household_key")
    ) or None
    household_name = _normalized_identifier(
        membership.get("household_name")
        or membership.get("name")
        or principal.get("household_name")
    ) or None

    return HouseholdContext(
        user_id=user_id or email,
        email=email,
        active_household_id=selected_household_id,
        household_key=household_key,
        household_name=household_name,
        role=role,
        display_role=display_household_role(role),
    )
