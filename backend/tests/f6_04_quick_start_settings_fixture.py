"""F6-04 setup: a pre-existing Inhuis halen household for UI settings recovery.

The actual settings mutation and failure/retry remain REAL browser actions.
Only this deterministic starting household is provisioned in the database.
"""
from __future__ import annotations

import os
from app.db import engine
from app.services.consumer_account_provisioning import provision_new_consumer_account
from app.services.household_onboarding_service import (
    advance_profile_to_shared_household_minimum,
    complete_household_onboarding,
    ensure_new_household_repurchase_default,
    select_primary_use_case,
)
from app.services.household_product_configuration_service import save_inhuis_halen_configuration


def run() -> int:
    email = os.environ["F6_04_SETTINGS_EMAIL"].strip().lower()
    password = os.environ["F6_04_SETTINGS_PASSWORD"]
    name = os.environ["F6_04_SETTINGS_HOUSEHOLD"].strip()
    assert email and password and name
    assert engine.dialect.name == "postgresql"

    with engine.begin() as conn:
        account = provision_new_consumer_account(
            conn, email=email, password=password, household_name=name,
        )
        select_primary_use_case(
            conn, household_id=account.household_id, primary_use_case="inhuis_halen",
        )
        config = save_inhuis_halen_configuration(
            conn,
            household_id=account.household_id,
            simple_inventory_enabled=True,
            almost_out_notifications_enabled=False,
            receipt_processing_enabled=False,
            recipes_enabled=False,
        )
        assert config.inventory_tracking_level == "quantity"
        advance_profile_to_shared_household_minimum(
            conn, household_id=account.household_id, expected_primary_use_case="inhuis_halen",
        )
        completed = complete_household_onboarding(
            conn,
            household_id=account.household_id,
            household_name=name,
            household_usage_mode="alone",
        )
        ensure_new_household_repurchase_default(conn, account.household_id)
        assert completed.onboarding_status == "completed"
        assert completed.primary_use_case == "inhuis_halen"

    print("F6_04_SETTINGS_FIXTURE_GREEN", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
