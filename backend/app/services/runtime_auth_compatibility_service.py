from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException


TOKEN_PREFIX = "rezzerv-dev-token::"

_CANONICAL_HOUSEHOLD_ROLES = {
    "owner": "huishouden.eigenaar",
    "eigenaar": "huishouden.eigenaar",
    "household.admin": "huishouden.eigenaar",
    "huishouden.eigenaar": "huishouden.eigenaar",
    "member": "huishouden.lid",
    "lid": "huishouden.lid",
    "household.member": "huishouden.lid",
    "household.advanced_member": "huishouden.lid",
    "huishouden.lid": "huishouden.lid",
    "viewer": "huishouden.kijker",
    "kijker": "huishouden.kijker",
    "household.viewer": "huishouden.kijker",
    "huishouden.kijker": "huishouden.kijker",
}

_DISPLAY_ROLES = {
    "huishouden.eigenaar": "Eigenaar",
    "huishouden.lid": "Lid",
    "huishouden.kijker": "Kijker",
}


@dataclass(frozen=True)
class RuntimeHouseholdRole:
    role_key: str
    display_role: str


def normalize_runtime_household_role(value: str | None) -> RuntimeHouseholdRole:
    normalized = str(value or "").strip().lower()
    role_key = _CANONICAL_HOUSEHOLD_ROLES.get(normalized)
    if role_key is None:
        raise ValueError(f"Onbekende huishoudrol: {value!r}")
    return RuntimeHouseholdRole(
        role_key=role_key,
        display_role=_DISPLAY_ROLES[role_key],
    )


def parse_explicit_runtime_token(authorization: str | None) -> str:
    """Resolve only an explicitly user-bound development token.

    The historical unscoped ``rezzerv-dev-token`` is deliberately rejected:
    it silently authenticated as ``admin@rezzerv.local`` and therefore mixed a
    household owner identity with central platform access.
    """

    header = str(authorization or "").strip()
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = header.split(" ", 1)[1].strip()
    if not token.startswith(TOKEN_PREFIX):
        raise HTTPException(status_code=401, detail="Unauthorized")

    email = token[len(TOKEN_PREFIX):].strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return email


def build_explicit_runtime_token(email: str) -> str:
    normalized_email = str(email or "").strip().lower()
    if not normalized_email or "@" not in normalized_email:
        raise ValueError("Een geldig e-mailadres is verplicht")
    return f"{TOKEN_PREFIX}{normalized_email}"
