"""Household-owned, non-destructive controls for locations and Uitpakken.

These are explicitly reversible preferences, unlike the additive onboarding
capability-expansion service. Existing stock and pending receipt work never
change or disappear as an implicit side-effect of a preference update.
"""
from __future__ import annotations

from sqlalchemy import text

from app.services.canonical_direct_location_service import ensure_canonical_direct_location
from app.services.household_product_configuration_service import (
    resolve_household_product_configuration,
)

_LOCATION_LEVELS = {"none": 0, "global": 1, "exact": 2}


def save_household_workflow_preferences(
    conn,
    *,
    household_id: str,
    location_tracking_level: str,
    unpacking_enabled: bool,
):
    household_id = str(household_id or "").strip()
    level = str(location_tracking_level or "").strip().lower()
    if not household_id:
        raise ValueError("Actief huishouden ontbreekt")
    if level not in _LOCATION_LEVELS:
        raise ValueError("Kies geen, globale of exacte voorraadlocaties")

    current = resolve_household_product_configuration(conn, household_id)
    unpacking = bool(unpacking_enabled)
    if level == "exact" and not unpacking:
        raise ValueError(
            "Exacte voorraadlocaties vereisen Uitpakken. Zet ook voorraadlocaties uit "
            "of kies globale locaties voordat je Uitpakken uitschakelt."
        )

    location_change = level != current.location_tracking_level
    unpacking_disabled = current.unpacking_enabled and not unpacking

    if location_change or unpacking_disabled:
        # A still-open receipt may need the existing Uitpakken choices. Do not
        # conceal that work by changing the household process underneath it.
        pending = conn.execute(text("""
            SELECT 1
            FROM purchase_import_batches pib
            JOIN purchase_import_lines pil ON pil.batch_id = pib.id
            WHERE pib.household_id = :household_id
              AND pib.source_type = 'receipt'
              AND COALESCE(pil.processing_status, 'pending') <> 'processed'
              AND COALESCE(pil.review_decision, 'pending') <> 'ignored'
            LIMIT 1
        """), {"household_id": household_id}).first()
        if pending:
            raise ValueError(
                "Er staan nog bonartikelen open in Uitpakken. Verwerk of handel deze eerst af; "
                "de bestaande bonartikelen worden niet automatisch overgeslagen."
            )

    if (
        _LOCATION_LEVELS[level] < _LOCATION_LEVELS[current.location_tracking_level]
        or (unpacking_disabled and level in {"none", "global"})
    ):
        # Old location-bound rows must not become invisible or be silently
        # mixed with new locationless receipts when Uitpakken is turned off.
        # No destructive conversion here.
        occupied = conn.execute(text("""
            SELECT 1
            FROM inventory
            WHERE household_id = :household_id
              AND COALESCE(status, 'active') = 'active'
              AND COALESCE(aantal, 0) > 0
              AND (space_id IS NOT NULL OR sublocation_id IS NOT NULL)
            LIMIT 1
        """), {"household_id": household_id}).first()
        if occupied:
            raise ValueError(
                "Deze wijziging kan nog niet: er staat actieve voorraad op locaties. "
                "Die voorraad en de historie blijven intact. Eerst is een "
                "gecontroleerde voorraadomzetting nodig voordat Uitpakken of "
                "locatiegebruik veilig kan worden uitgezet."
            )

    if location_change or current.unpacking_enabled != unpacking:
        conn.execute(text("""
            UPDATE household_product_configuration
            SET location_tracking_level = :location_tracking_level,
                unpacking_enabled = :unpacking_enabled,
                updated_at = CURRENT_TIMESTAMP
            WHERE household_id = :household_id
        """), {
            "household_id": household_id,
            "location_tracking_level": level,
            "unpacking_enabled": int(unpacking),
        })
        if level == "global":
            ensure_canonical_direct_location(conn, household_id=household_id)

    return resolve_household_product_configuration(conn, household_id)
