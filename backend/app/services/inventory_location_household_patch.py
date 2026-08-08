from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text


def _required_household_id(household_id: Any) -> str:
    normalized = str(household_id or "").strip()
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="Actief huishouden ontbreekt voor locatie-resolutie",
        )
    return normalized


def resolve_space_id(
    conn,
    household_id: Any,
    space_id: Any = None,
    space_name: Any = None,
) -> str | None:
    """Resolve or create a space strictly inside one active household."""

    normalized_household_id = _required_household_id(household_id)
    normalized_space_id = str(space_id or "").strip()
    normalized_space_name = " ".join(str(space_name or "").strip().split())

    if normalized_space_id:
        existing = conn.execute(
            text(
                """
                SELECT id
                FROM spaces
                WHERE id = :id
                  AND household_id = :household_id
                LIMIT 1
                """
            ),
            {
                "id": normalized_space_id,
                "household_id": normalized_household_id,
            },
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="Ruimte niet gevonden")
        return str(existing["id"])

    if not normalized_space_name:
        return None

    existing = conn.execute(
        text(
            """
            SELECT id
            FROM spaces
            WHERE household_id = :household_id
              AND lower(trim(naam)) = lower(trim(:naam))
            LIMIT 1
            """
        ),
        {
            "household_id": normalized_household_id,
            "naam": normalized_space_name,
        },
    ).mappings().first()
    if existing:
        return str(existing["id"])

    new_space_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO spaces (id, naam, household_id)
            VALUES (:id, :naam, :household_id)
            """
        ),
        {
            "id": new_space_id,
            "naam": normalized_space_name,
            "household_id": normalized_household_id,
        },
    )
    return new_space_id


def resolve_sublocation_id(
    conn,
    household_id: Any,
    space_id: Any,
    sublocation_id: Any = None,
    sublocation_name: Any = None,
) -> str | None:
    """Resolve or create a sublocation only below a space in the household."""

    normalized_household_id = _required_household_id(household_id)
    normalized_space_id = str(space_id or "").strip()
    normalized_sublocation_id = str(sublocation_id or "").strip()
    normalized_sublocation_name = " ".join(
        str(sublocation_name or "").strip().split()
    )

    if normalized_sublocation_id:
        existing = conn.execute(
            text(
                """
                SELECT sl.id
                FROM sublocations sl
                JOIN spaces s ON s.id = sl.space_id
                WHERE sl.id = :id
                  AND s.household_id = :household_id
                LIMIT 1
                """
            ),
            {
                "id": normalized_sublocation_id,
                "household_id": normalized_household_id,
            },
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=404, detail="Sublocatie niet gevonden")
        return str(existing["id"])

    if not normalized_space_id or not normalized_sublocation_name:
        return None

    parent_space = conn.execute(
        text(
            """
            SELECT id
            FROM spaces
            WHERE id = :space_id
              AND household_id = :household_id
            LIMIT 1
            """
        ),
        {
            "space_id": normalized_space_id,
            "household_id": normalized_household_id,
        },
    ).mappings().first()
    if not parent_space:
        raise HTTPException(status_code=404, detail="Ruimte niet gevonden")

    existing = conn.execute(
        text(
            """
            SELECT sl.id
            FROM sublocations sl
            JOIN spaces s ON s.id = sl.space_id
            WHERE sl.space_id = :space_id
              AND s.household_id = :household_id
              AND lower(trim(sl.naam)) = lower(trim(:naam))
            LIMIT 1
            """
        ),
        {
            "space_id": normalized_space_id,
            "household_id": normalized_household_id,
            "naam": normalized_sublocation_name,
        },
    ).mappings().first()
    if existing:
        return str(existing["id"])

    new_sublocation_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO sublocations (id, naam, space_id)
            SELECT :id, :naam, s.id
            FROM spaces s
            WHERE s.id = :space_id
              AND s.household_id = :household_id
            """
        ),
        {
            "id": new_sublocation_id,
            "naam": normalized_sublocation_name,
            "space_id": normalized_space_id,
            "household_id": normalized_household_id,
        },
    )
    return new_sublocation_id


def install_inventory_location_household_patch(main_module) -> None:
    """Replace legacy inventory location helpers after app.main is loaded."""

    main_module._dev_resolve_space_id = resolve_space_id
    main_module._dev_resolve_sublocation_id = resolve_sublocation_id
