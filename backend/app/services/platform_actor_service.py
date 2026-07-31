from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from fastapi import HTTPException

from app.services.authorization_foundation_service import (
    ensure_authorization_foundation,
    evaluate_platform_permission,
)

SUPERGEBRUIKER_EMAIL = "supergebruiker@rezzerv.local"
SUPERGEBRUIKER_HUISHOUDEN_ID = "0"


@dataclass(frozen=True)
class PlatformActor:
    user_id: str
    email: str
    name: str
    role: str
    role_key: str

    @property
    def is_supergebruiker(self) -> bool:
        return self.role_key == "platform.supergebruiker"

    @property
    def is_frontteam(self) -> bool:
        return self.role_key == "platform.frontteam"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def resolve_platform_actor(conn, *, runtime_user: Mapping[str, Any], permission_key: str) -> PlatformActor:
    """Bepaal een centrale actor uitsluitend op basis van centrale rollen.

    Een huishoudrol zoals Eigenaar of de historische rol admin verleent hier nooit
    zelfstandig centrale toegang.
    """
    actor = _mapping(runtime_user)
    email = str(actor.get("email") or actor.get("user_id") or actor.get("id") or "").strip().lower()
    user_id = str(actor.get("user_id") or actor.get("id") or email).strip().lower()
    if not email or not user_id:
        raise HTTPException(status_code=403, detail="Centrale gebruiker heeft geen bruikbare identiteit")

    ensure_authorization_foundation(conn)
    decision = evaluate_platform_permission(conn, user_id=user_id, permission_key=permission_key)
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=f"Ontbrekende centrale bevoegdheid: {permission_key}")

    role_key = str(decision.granted_by or "").strip()
    if role_key not in {"platform.supergebruiker", "platform.frontteam"}:
        raise HTTPException(status_code=403, detail="Geen geldige centrale rol gevonden")

    role = "Supergebruiker" if role_key == "platform.supergebruiker" else "Frontteam"
    name = str(actor.get("name") or actor.get("display_name") or email).strip() or email
    return PlatformActor(user_id=user_id, email=email, name=name, role=role, role_key=role_key)


def assert_platform_household_mutation_allowed(*, actor: PlatformActor, household_id: str | int | None) -> None:
    """Beperk centrale huishoudmutaties tot huishouden 0.

    Frontteam krijgt via deze centrale route geen huishoudmutatierecht. De
    Supergebruiker mag uitsluitend huishoudgegevens van het testhuishouden 0
    wijzigen.
    """
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise HTTPException(status_code=400, detail="Huishouden ontbreekt")
    if actor.is_frontteam:
        raise HTTPException(status_code=403, detail="Frontteam mag geen huishoudgegevens wijzigen")
    if actor.is_supergebruiker and normalized_household_id != SUPERGEBRUIKER_HUISHOUDEN_ID:
        raise HTTPException(
            status_code=403,
            detail="De Supergebruiker mag huishoudgegevens alleen wijzigen in huishouden 0",
        )
