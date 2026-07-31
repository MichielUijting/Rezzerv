from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import text

from app.services.platform_actor_service import (
    PlatformActor,
    SUPERGEBRUIKER_HUISHOUDEN_ID,
)


@dataclass(frozen=True)
class SupportHouseholdScope:
    unrestricted: bool
    household_ids: tuple[str, ...]

    def allows(self, household_id: str | int | None) -> bool:
        normalized = str(household_id or "").strip()
        return bool(normalized) and (self.unrestricted or normalized in self.household_ids)


def resolve_support_household_scope(conn, *, actor: PlatformActor) -> SupportHouseholdScope:
    """Bepaal het server-side Meldingenbereik van een centrale gebruiker.

    De Supergebruiker behoudt het centrale totaaloverzicht. Frontteam ziet en
    benadert alleen huishouden 0 en huishoudens waarvan het Frontteamlid zelf
    een actief lidmaatschap heeft. De browser bepaalt deze scope nooit.
    """
    if actor.is_supergebruiker:
        return SupportHouseholdScope(unrestricted=True, household_ids=())

    if not actor.is_frontteam:
        raise HTTPException(status_code=403, detail="Geen geldige centrale Meldingenrol")

    rows = conn.execute(text("""
        SELECT DISTINCT household_id
        FROM household_memberships
        WHERE lower(user_email) = :email
          AND trim(COALESCE(household_id, '')) <> ''
        ORDER BY household_id
    """), {"email": actor.email}).mappings().all()

    household_ids = {SUPERGEBRUIKER_HUISHOUDEN_ID}
    household_ids.update(
        str(row.get("household_id") or "").strip()
        for row in rows
        if str(row.get("household_id") or "").strip()
    )
    return SupportHouseholdScope(
        unrestricted=False,
        household_ids=tuple(sorted(household_ids)),
    )


def assert_support_household_allowed(
    conn,
    *,
    actor: PlatformActor,
    household_id: str | int | None,
) -> SupportHouseholdScope:
    normalized = str(household_id or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Huishouden ontbreekt")

    scope = resolve_support_household_scope(conn, actor=actor)
    if not scope.allows(normalized):
        raise HTTPException(
            status_code=403,
            detail="Frontteam heeft alleen toegang tot huishouden 0 en eigen huishoudens",
        )
    return scope
