from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text

from app.services.household_product_configuration_service import (
    resolve_household_product_configuration,
)


LOCATION_NONE = "none"
LOCATION_GLOBAL = "global"
LOCATION_EXACT = "exact"


def _normalize(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _household_id(value: Any) -> str:
    normalized = _normalize(value)
    if not normalized:
        raise HTTPException(status_code=400, detail="Actief huishouden ontbreekt")
    return normalized


def _locationless_payload() -> dict[str, Any]:
    return {
        "location_id": None,
        "space_id": None,
        "sublocation_id": None,
        "location_label": "",
    }


def _resolve_owned_space(conn, household_id: str, space_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            """
            SELECT id, naam
            FROM spaces
            WHERE id = :space_id
              AND household_id = :household_id
              AND COALESCE(active, 1) = 1
            LIMIT 1
            """
        ),
        {"space_id": space_id, "household_id": household_id},
    ).mappings().first()
    return dict(row) if row else None


def _resolve_owned_sublocation(conn, household_id: str, sublocation_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            """
            SELECT sl.id AS sublocation_id,
                   sl.space_id,
                   sl.naam AS sublocation_name,
                   s.naam AS space_name
            FROM sublocations sl
            JOIN spaces s ON s.id = sl.space_id
            WHERE sl.id = :sublocation_id
              AND s.household_id = :household_id
              AND COALESCE(sl.active, 1) = 1
              AND COALESCE(s.active, 1) = 1
            LIMIT 1
            """
        ),
        {"sublocation_id": sublocation_id, "household_id": household_id},
    ).mappings().first()
    return dict(row) if row else None


def _space_has_active_sublocations(conn, household_id: str, space_id: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT 1
                FROM sublocations sl
                JOIN spaces s ON s.id = sl.space_id
                WHERE sl.space_id = :space_id
                  AND s.household_id = :household_id
                  AND COALESCE(sl.active, 1) = 1
                  AND COALESCE(s.active, 1) = 1
                LIMIT 1
                """
            ),
            {"space_id": space_id, "household_id": household_id},
        ).scalar()
    )


def resolve_inventory_location(
    conn,
    household_id: Any,
    *,
    space_id: Any = None,
    sublocation_id: Any = None,
) -> dict[str, Any]:
    """Resolve an inventory location according to the household product configuration.

    `none` stores a real NULL/NULL location and rejects supplied location identifiers.
    `global` requires one owned active main space and rejects sublocations.
    `exact` preserves the terminal-location rule: an active sublocation, or an active
    main space only when that space has no active sublocations.
    """

    normalized_household_id = _household_id(household_id)
    normalized_space_id = _normalize(space_id)
    normalized_sublocation_id = _normalize(sublocation_id)
    configuration = resolve_household_product_configuration(conn, normalized_household_id)
    level = configuration.location_tracking_level

    if level == LOCATION_NONE:
        if normalized_space_id or normalized_sublocation_id:
            raise HTTPException(
                status_code=400,
                detail="Dit huishouden gebruikt voorraad zonder locatie; space_id en sublocation_id zijn niet toegestaan",
            )
        return _locationless_payload()

    if level == LOCATION_GLOBAL:
        if normalized_sublocation_id:
            raise HTTPException(
                status_code=400,
                detail="Dit huishouden gebruikt alleen hoofdruimtes; sublocation_id is niet toegestaan",
            )
        if not normalized_space_id:
            raise HTTPException(
                status_code=400,
                detail="Een hoofdruimte is verplicht voor dit huishouden",
            )
        space = _resolve_owned_space(conn, normalized_household_id, normalized_space_id)
        if not space:
            raise HTTPException(status_code=404, detail="Ruimte niet gevonden binnen actief huishouden")
        return {
            "location_id": str(space["id"]),
            "space_id": str(space["id"]),
            "sublocation_id": None,
            "location_label": str(space.get("naam") or ""),
        }

    if level != LOCATION_EXACT:
        raise HTTPException(status_code=500, detail="Ongeldig locatieniveau in productconfiguratie")

    if normalized_sublocation_id:
        sublocation = _resolve_owned_sublocation(
            conn,
            normalized_household_id,
            normalized_sublocation_id,
        )
        if not sublocation:
            raise HTTPException(status_code=404, detail="Sublocatie niet gevonden binnen actief huishouden")
        resolved_space_id = str(sublocation["space_id"])
        if normalized_space_id and normalized_space_id != resolved_space_id:
            raise HTTPException(status_code=400, detail="sublocation_id hoort niet bij de gekozen ruimte")
        return {
            "location_id": str(sublocation["sublocation_id"]),
            "space_id": resolved_space_id,
            "sublocation_id": str(sublocation["sublocation_id"]),
            "location_label": f"{sublocation['space_name']} / {sublocation['sublocation_name']}",
        }

    if not normalized_space_id:
        raise HTTPException(status_code=400, detail="Een exacte voorraadlocatie is verplicht voor dit huishouden")

    space = _resolve_owned_space(conn, normalized_household_id, normalized_space_id)
    if not space:
        raise HTTPException(status_code=404, detail="Ruimte niet gevonden binnen actief huishouden")
    if _space_has_active_sublocations(conn, normalized_household_id, normalized_space_id):
        raise HTTPException(
            status_code=400,
            detail="Kies een sublocatie binnen deze ruimte, of kies een ruimte zonder sublocaties",
        )
    return {
        "location_id": str(space["id"]),
        "space_id": str(space["id"]),
        "sublocation_id": None,
        "location_label": str(space.get("naam") or ""),
    }


def resolve_inventory_target_location(
    conn,
    household_id: Any,
    target_location_id: Any = None,
) -> dict[str, Any]:
    """Resolve the single target id used by receipt/Uitpakken flows through the same policy."""

    normalized_household_id = _household_id(household_id)
    normalized_target_id = _normalize(target_location_id)
    configuration = resolve_household_product_configuration(conn, normalized_household_id)
    level = configuration.location_tracking_level

    if level == LOCATION_NONE:
        if normalized_target_id:
            raise HTTPException(
                status_code=400,
                detail="Dit huishouden gebruikt voorraad zonder locatie; target_location_id is niet toegestaan",
            )
        return _locationless_payload()

    if not normalized_target_id:
        if level == LOCATION_GLOBAL:
            raise HTTPException(status_code=400, detail="Een hoofdruimte is verplicht voor dit huishouden")
        raise HTTPException(status_code=400, detail="Een exacte voorraadlocatie is verplicht voor dit huishouden")

    if level == LOCATION_GLOBAL:
        return resolve_inventory_location(
            conn,
            normalized_household_id,
            space_id=normalized_target_id,
        )

    if level != LOCATION_EXACT:
        raise HTTPException(status_code=500, detail="Ongeldig locatieniveau in productconfiguratie")

    sublocation = _resolve_owned_sublocation(conn, normalized_household_id, normalized_target_id)
    if sublocation:
        return resolve_inventory_location(
            conn,
            normalized_household_id,
            sublocation_id=normalized_target_id,
        )
    return resolve_inventory_location(
        conn,
        normalized_household_id,
        space_id=normalized_target_id,
    )
