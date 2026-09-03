from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text

from app.services.household_product_configuration_service import (
    resolve_household_product_configuration,
)
from app.services.inventory_location_policy_service import (
    LOCATION_GLOBAL,
    resolve_inventory_target_location,
)


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


def _owned_active_sublocation_parent(
    conn,
    household_id: Any,
    target_location_id: Any,
) -> dict[str, str] | None:
    normalized_household_id = _required_household_id(household_id)
    normalized_target_id = str(target_location_id or "").strip()
    if not normalized_target_id:
        return None

    row = conn.execute(
        text(
            """
            SELECT
                s.id AS space_id,
                s.naam AS space_name,
                sl.id AS sublocation_id,
                sl.naam AS sublocation_name
            FROM sublocations sl
            JOIN spaces s ON s.id = sl.space_id
            WHERE sl.id = :target_location_id
              AND s.household_id = :household_id
              AND COALESCE(sl.active, TRUE) = TRUE
              AND COALESCE(s.active, TRUE) = TRUE
            LIMIT 1
            """
        ),
        {
            "target_location_id": normalized_target_id,
            "household_id": normalized_household_id,
        },
    ).mappings().first()
    if not row:
        return None
    return {
        "space_id": str(row["space_id"]),
        "space_name": str(row.get("space_name") or ""),
        "sublocation_id": str(row["sublocation_id"]),
        "sublocation_name": str(row.get("sublocation_name") or ""),
    }


def normalize_persisted_purchase_import_target_location(
    conn,
    household_id: Any,
    target_location_id: Any,
) -> dict[str, Any] | None:
    """Resolve persisted targets while repairing the old global/sublocation mismatch.

    The canonical global-location policy remains strict: new input must be a main
    space. This compatibility path exists only for purchase-import rows that were
    persisted by the older Uitpakken endpoint before that endpoint consulted the
    household product configuration. If such a stored id points to an owned active
    sublocation, processing safely degrades it to the parent main space.
    """

    normalized_household_id = _required_household_id(household_id)
    normalized_target_id = str(target_location_id or "").strip()

    try:
        return resolve_inventory_target_location(
            conn,
            normalized_household_id,
            normalized_target_id or None,
        )
    except HTTPException:
        pass

    configuration = resolve_household_product_configuration(
        conn,
        normalized_household_id,
    )
    if configuration.location_tracking_level != LOCATION_GLOBAL:
        return None

    parent = _owned_active_sublocation_parent(
        conn,
        normalized_household_id,
        normalized_target_id,
    )
    if not parent:
        return None

    try:
        return resolve_inventory_target_location(
            conn,
            normalized_household_id,
            parent["space_id"],
        )
    except HTTPException:
        return None


def validate_purchase_import_target_location_for_policy(
    conn,
    household_id: Any,
    target_location_id: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate new Uitpakken location choices against the household policy."""

    normalized_household_id = _required_household_id(household_id)
    normalized_target_id = str(target_location_id or "").strip()
    if not normalized_target_id:
        return None, None

    try:
        return (
            resolve_inventory_target_location(
                conn,
                normalized_household_id,
                normalized_target_id,
            ),
            None,
        )
    except HTTPException as exc:
        detail = str(exc.detail or "Ongeldige locatie gekozen")

    configuration = resolve_household_product_configuration(
        conn,
        normalized_household_id,
    )
    if configuration.location_tracking_level == LOCATION_GLOBAL:
        parent = _owned_active_sublocation_parent(
            conn,
            normalized_household_id,
            normalized_target_id,
        )
        if parent:
            return (
                None,
                "Dit huishouden gebruikt alleen hoofdlocaties. "
                f"Kies {parent['space_name']} in plaats van "
                f"{parent['space_name']} / {parent['sublocation_name']}.",
            )

    return None, detail


def install_inventory_location_household_patch(main_module) -> None:
    """Replace legacy inventory location helpers after app.main is loaded."""

    main_module._dev_resolve_space_id = resolve_space_id
    main_module._dev_resolve_sublocation_id = resolve_sublocation_id

    from .purchase_import_location_policy_patch import (
        _processing_household_id,
        install_purchase_import_location_policy_patch,
    )
    from .inventory_location_event_policy_patch import (
        install_inventory_location_event_policy_patch,
    )

    install_purchase_import_location_policy_patch(main_module)

    strict_process_resolver = main_module.resolve_store_storage_target_location
    original_target_validator = main_module.validate_purchase_import_storage_target_location

    def process_resolver_with_global_legacy_compat(conn, target_location_id):
        resolved = strict_process_resolver(conn, target_location_id)
        if resolved is not None:
            return resolved

        household_id = _processing_household_id.get()
        if not household_id:
            return None
        return normalize_persisted_purchase_import_target_location(
            conn,
            household_id,
            target_location_id,
        )

    def validate_target_location_with_household_policy(conn, line_id, target_location_id):
        line_ref = main_module.build_purchase_import_line_reference(conn, line_id)
        if not target_location_id:
            return None, line_ref

        household_id = conn.execute(
            text(
                """
                SELECT pib.household_id
                FROM purchase_import_lines pil
                JOIN purchase_import_batches pib ON pib.id = pil.batch_id
                WHERE pil.id = :line_id
                LIMIT 1
                """
            ),
            {"line_id": str(line_id)},
        ).scalar()
        if not household_id:
            return original_target_validator(conn, line_id, target_location_id)

        resolved, error_message = validate_purchase_import_target_location_for_policy(
            conn,
            str(household_id),
            target_location_id,
        )
        if resolved is not None:
            return resolved, line_ref

        line_ref["location_error_reason"] = "invalid_for_household_location_policy"
        line_ref["location_error_message"] = (
            error_message or "Ongeldige locatie voor de instellingen van dit huishouden."
        )
        return None, line_ref

    main_module.resolve_store_storage_target_location = (
        process_resolver_with_global_legacy_compat
    )
    main_module.validate_purchase_import_storage_target_location = (
        validate_target_location_with_household_policy
    )

    install_inventory_location_event_policy_patch(main_module)
