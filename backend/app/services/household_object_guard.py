"""Household ownership guard for household-scoped rows.

Use this guard after reading an object and before returning or mutating it. Query
filters should still include household_id; this guard is the second line of
defence against accidental cross-household access.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.household_context_service import HouseholdAccessDenied, HouseholdContext


def assert_row_in_household(
    context: HouseholdContext,
    row: Mapping[str, Any] | None,
    *,
    household_field: str = "household_id",
) -> Mapping[str, Any]:
    if row is None:
        raise HouseholdAccessDenied("Object bestaat niet binnen het actieve huishouden")

    row_household_id = str(row.get(household_field) or "").strip()
    if not row_household_id:
        raise HouseholdAccessDenied("Object mist een geldige huishoudkoppeling")
    if row_household_id != context.active_household_id:
        raise HouseholdAccessDenied("Geen toegang tot dit object binnen het actieve huishouden")
    return row


def household_where_parameters(context: HouseholdContext) -> dict[str, str]:
    """Canonical SQL parameter payload for household-scoped queries."""

    return {"household_id": context.active_household_id}
