"""Inhuis maintenance state contract.

Pure validation only: NOT wired to API, DB, scheduler or production.
Persisted admission/lease arbitration must be implemented before use.
"""
from __future__ import annotations

from enum import Enum


class MaintenanceState(str, Enum):
    NORMAL = "normal"
    ANNOUNCED = "announced"
    DRAINING = "draining"
    LOCKED = "locked"
    VERIFYING = "verifying"
    BLOCKED = "blocked"


class MaintenanceTransitionError(ValueError):
    """Unsafe, stale, or unauthorized transition was requested."""


_ALLOWED = {
    MaintenanceState.NORMAL: frozenset({MaintenanceState.ANNOUNCED}),
    MaintenanceState.ANNOUNCED: frozenset({MaintenanceState.DRAINING, MaintenanceState.NORMAL}),
    MaintenanceState.DRAINING: frozenset({MaintenanceState.LOCKED, MaintenanceState.BLOCKED}),
    MaintenanceState.LOCKED: frozenset({MaintenanceState.VERIFYING, MaintenanceState.BLOCKED}),
    MaintenanceState.VERIFYING: frozenset({MaintenanceState.NORMAL, MaintenanceState.BLOCKED}),
    MaintenanceState.BLOCKED: frozenset({MaintenanceState.VERIFYING}),
}
_WRITES_ALLOWED = frozenset({MaintenanceState.NORMAL, MaintenanceState.ANNOUNCED})


def allows_new_writes(state: MaintenanceState) -> bool:
    """Conservative read-only projection; never use as a race-safe admission lock."""
    return MaintenanceState(state) in _WRITES_ALLOWED


def validate_transition(
    current: MaintenanceState,
    target: MaintenanceState,
    *,
    authorized: bool,
    active_writers: int | None = None,
    runtime_verified: bool = False,
) -> None:
    """Validate an intended transition, not execute one.

    This does not establish real-time writer quiescence or database isolation.
    Such proof must come from durable PostgreSQL arbitration.
    """
    if not authorized:
        raise MaintenanceTransitionError("Bevoegde platformbeheerder vereist")
    current, target = MaintenanceState(current), MaintenanceState(target)
    if target not in _ALLOWED[current]:
        raise MaintenanceTransitionError("Ongeldige onderhoudsovergang")
    if target == MaintenanceState.LOCKED:
        if active_writers is None or active_writers != 0:
            raise MaintenanceTransitionError("Actieve verwerking onbekend of niet afgerond")
        if not runtime_verified:
            raise MaintenanceTransitionError("Geen geverifieerd drainbewijs")
    if current == MaintenanceState.VERIFYING and target == MaintenanceState.NORMAL:
        if not runtime_verified:
            raise MaintenanceTransitionError("Herstelcontroles niet voltooid")
    if target == MaintenanceState.VERIFYING and not runtime_verified:
        raise MaintenanceTransitionError("Herstartomgeving niet geverifieerd")
