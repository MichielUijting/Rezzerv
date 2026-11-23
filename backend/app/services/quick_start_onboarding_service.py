"""Atomic one-click defaults for a new regular Inhuis household.

Keep this helper shared by first registration and a later additional household.
It never applies to existing/completed household configurations.
"""

from app.services.household_onboarding_service import (
    ONBOARDING_STATUS_NOT_STARTED,
    advance_profile_to_shared_household_minimum,
    complete_household_onboarding,
    ensure_new_household_repurchase_default,
    resolve_household_onboarding_state,
    select_primary_use_case,
)
from app.services.household_product_configuration_service import save_wat_inhuis_configuration
from app.services.receipt_historical_import_policy import activate_cutover_for_new_onboarding


def complete_default_wat_inhuis_onboarding(conn, *, household_id: str, household_name: str):
    current = resolve_household_onboarding_state(conn, household_id)
    if current.onboarding_status != ONBOARDING_STATUS_NOT_STARTED:
        raise ValueError("Snel starten kan alleen voor een nieuw, nog niet ingericht huishouden")

    select_primary_use_case(
        conn, household_id=household_id, primary_use_case="wat_inhuis",
    )
    configuration = save_wat_inhuis_configuration(
        conn,
        household_id=household_id,
        inventory_tracking_level="quantity",
        global_locations_enabled=False,
        almost_out_enabled=True,
        shopping_enabled=True,
    )
    advance_profile_to_shared_household_minimum(
        conn, household_id=household_id, expected_primary_use_case="wat_inhuis",
    )
    state = complete_household_onboarding(
        conn,
        household_id=household_id,
        household_name=household_name,
        household_usage_mode="alone",
    )
    ensure_new_household_repurchase_default(conn, household_id)
    if configuration.receipt_processing_enabled:
        activate_cutover_for_new_onboarding(conn, household_id=household_id)
    return state, configuration
