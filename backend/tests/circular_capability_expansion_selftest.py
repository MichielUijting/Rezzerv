from __future__ import annotations

from sqlalchemy import text

from app.services.household_capability_expansion_service import (
    expand_with_wat_inhuis,
    expand_with_waar_inhuis,
)
from app.services.household_location_onboarding_service import (
    ensure_location_foundation,
    provision_waar_inhuis_expansion_locations,
)
from app.services.household_product_configuration_service import (
    save_inhuis_halen_configuration,
)
from app.services.household_product_use_case_service import (
    activate_household_product_use_case,
    resolve_active_household_product_use_cases,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
    seed_household,
)


def run() -> None:
    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    try:
        with engine.begin() as conn:
            seed_household(conn, household_id="h1", name="Circulair huishouden 1")
            seed_household(conn, household_id="h2", name="Circulair huishouden 2")

            # Model an already completed Inhuis halen capability. The route activates
            # the use case separately from persisting its product configuration.
            initial = save_inhuis_halen_configuration(
                conn,
                household_id="h1",
                simple_inventory_enabled=True,
                almost_out_notifications_enabled=True,
                receipt_processing_enabled=True,
                recipes_enabled=True,
            )
            activate_household_product_use_case(
                conn,
                household_id="h1",
                use_case="inhuis_halen",
            )
            assert initial.inventory_tracking_level == "quantity"
            assert initial.location_tracking_level == "none"
            assert initial.shopping_enabled is True
            assert initial.receipt_processing_enabled is True
            assert initial.recipes_enabled is True

            # Expansion is deliberately monotonic. Requesting presence may not
            # downgrade an existing quantity capability, and False values do not
            # switch off capabilities that were already active.
            after_wat = expand_with_wat_inhuis(
                conn,
                household_id="h1",
                inventory_tracking_level="presence",
                global_locations_enabled=True,
                almost_out_enabled=False,
                shopping_enabled=False,
            )
            activate_household_product_use_case(
                conn,
                household_id="h1",
                use_case="wat_inhuis",
            )
            assert after_wat.inventory_tracking_level == "quantity"
            assert after_wat.location_tracking_level == "global"
            assert after_wat.almost_out_enabled is True
            assert after_wat.almost_out_notifications_enabled is True
            assert after_wat.shopping_enabled is True
            assert after_wat.receipt_processing_enabled is True
            assert after_wat.recipes_enabled is True

            active = resolve_active_household_product_use_cases(
                conn,
                household_id="h1",
            )
            assert active == ["inhuis_halen", "wat_inhuis"]

            # Re-applying a lower location request and the same inventory level must
            # likewise preserve the stronger already active configuration.
            after_wat_again = expand_with_wat_inhuis(
                conn,
                household_id="h1",
                inventory_tracking_level="quantity",
                global_locations_enabled=False,
                almost_out_enabled=True,
                shopping_enabled=True,
            )
            assert after_wat_again.inventory_tracking_level == "quantity"
            assert after_wat_again.location_tracking_level == "global"
            assert after_wat_again.almost_out_enabled is True
            assert after_wat_again.almost_out_notifications_enabled is True
            assert after_wat_again.shopping_enabled is True
            assert after_wat_again.receipt_processing_enabled is True
            assert after_wat_again.recipes_enabled is True

            after_waar = expand_with_waar_inhuis(
                conn,
                household_id="h1",
                unpacking_enabled=True,
                receipt_processing_enabled=False,
                almost_out_enabled=False,
            )
            activate_household_product_use_case(
                conn,
                household_id="h1",
                use_case="waar_inhuis",
            )
            assert after_waar.inventory_tracking_level == "quantity"
            assert after_waar.location_tracking_level == "exact"
            assert after_waar.unpacking_enabled is True
            assert after_waar.receipt_processing_enabled is True
            assert after_waar.almost_out_enabled is True
            assert after_waar.almost_out_notifications_enabled is True
            assert after_waar.shopping_enabled is True
            assert after_waar.recipes_enabled is True

            active = resolve_active_household_product_use_cases(
                conn,
                household_id="h1",
            )
            assert active == ["inhuis_halen", "wat_inhuis", "waar_inhuis"]

            # Location management remains explicit and separate from capability
            # activation; exercise the settings-owned provisioning helper directly.
            ensure_location_foundation(conn)
            provisioned = provision_waar_inhuis_expansion_locations(
                conn,
                household_id="h1",
                main_locations=["Keuken", "Voorraadkast"],
                sublocations=[],
            )
            assert [row["name"] for row in provisioned["spaces"]] == [
                "Keuken",
                "Voorraadkast",
            ]
            assert provisioned["sublocations"] == []
            persisted = conn.execute(
                text(
                    "SELECT naam FROM spaces WHERE household_id = :household_id ORDER BY naam"
                ),
                {"household_id": "h1"},
            ).scalars().all()
            assert persisted == ["Keuken", "Voorraadkast"]

            activate_household_product_use_case(
                conn,
                household_id="h2",
                use_case="wat_inhuis",
            )
            active_h2 = resolve_active_household_product_use_cases(
                conn,
                household_id="h2",
            )
            assert active_h2 == ["wat_inhuis"]
    finally:
        engine.dispose()

    print("CIRCULAR_CAPABILITY_EXPANSION_BACKEND_GREEN")
    print("CIRCULAR_CAPABILITY_EXPANSION_GREEN")


if __name__ == "__main__":
    run()
