"""Validation for Onboarding v2 step F product-aware navigation projection."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.api.household_onboarding_routes import _public_onboarding_with_product_configuration
from app.services.household_onboarding_service import (
    HouseholdOnboardingState,
    ONBOARDING_STATUS_COMPLETED,
)
from app.services.household_product_configuration_service import (
    resolve_household_product_configuration,
    save_inhuis_halen_configuration,
    save_wat_inhuis_configuration,
    save_waar_inhuis_configuration,
)


def _state(household_id: str, primary_use_case: str | None) -> HouseholdOnboardingState:
    return HouseholdOnboardingState(
        household_id=household_id,
        household_name=f"Huishouden {household_id}",
        onboarding_status=ONBOARDING_STATUS_COMPLETED,
        onboarding_version=2,
        primary_use_case=primary_use_case,
        onboarding_step=None,
        household_usage_mode="alone",
        onboarding_completed_at="2026-08-23T20:00:00Z",
    )


def run() -> int:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    checks: list[str] = []

    with engine.begin() as conn:
        legacy_payload = _public_onboarding_with_product_configuration(
            conn,
            _state("legacy-household", None),
            can_manage=True,
        )
        assert legacy_payload["product_configuration"] is None
        checks.append("legacy_household_without_configuration_projects_null")

        save_inhuis_halen_configuration(
            conn,
            household_id="inhuis-halen-household",
            simple_inventory_enabled=True,
            almost_out_notifications_enabled=True,
            receipt_processing_enabled=True,
            recipes_enabled=False,
        )
        inhuis_payload = _public_onboarding_with_product_configuration(
            conn,
            _state("inhuis-halen-household", "inhuis_halen"),
            can_manage=True,
        )
        inhuis_config = inhuis_payload["product_configuration"]
        assert inhuis_config["inventory_tracking_level"] == "quantity"
        assert inhuis_config["location_tracking_level"] == "none"
        assert inhuis_config["shopping_enabled"] is True
        assert inhuis_config["almost_out_enabled"] is True
        assert inhuis_config["receipt_processing_enabled"] is True
        checks.append("inhuis_halen_configuration_is_projected")

        save_inhuis_halen_configuration(
            conn,
            household_id="inhuis-halen-no-kassa-household",
            simple_inventory_enabled=True,
            almost_out_notifications_enabled=False,
            receipt_processing_enabled=False,
            recipes_enabled=False,
        )
        inhuis_no_kassa_payload = _public_onboarding_with_product_configuration(
            conn,
            _state("inhuis-halen-no-kassa-household", "inhuis_halen"),
            can_manage=True,
        )
        assert (
            inhuis_no_kassa_payload["product_configuration"]["receipt_processing_enabled"]
            is False
        )
        assert (
            resolve_household_product_configuration(
                conn,
                "inhuis-halen-no-kassa-household",
            ).receipt_processing_enabled
            is False
        )
        checks.append("non_wat_inhuis_configuration_is_not_upgraded")

        save_wat_inhuis_configuration(
            conn,
            household_id="wat-inhuis-household",
            inventory_tracking_level="presence",
            global_locations_enabled=True,
            almost_out_enabled=False,
            shopping_enabled=True,
        )
        conn.execute(text("""
            UPDATE household_product_configuration
            SET receipt_processing_enabled = 0
            WHERE household_id = :household_id
        """), {"household_id": "wat-inhuis-household"})
        assert (
            resolve_household_product_configuration(
                conn,
                "wat-inhuis-household",
            ).receipt_processing_enabled
            is False
        )

        wat_payload = _public_onboarding_with_product_configuration(
            conn,
            _state("wat-inhuis-household", "wat_inhuis"),
            can_manage=False,
        )
        wat_config = wat_payload["product_configuration"]
        assert wat_payload["can_manage"] is False
        assert wat_config["inventory_tracking_level"] == "presence"
        assert wat_config["location_tracking_level"] == "global"
        assert wat_config["shopping_enabled"] is True
        assert wat_config["receipt_processing_enabled"] is True
        assert wat_config["unpacking_enabled"] is False
        assert (
            resolve_household_product_configuration(
                conn,
                "wat-inhuis-household",
            ).receipt_processing_enabled
            is True
        )
        checks.append("legacy_wat_inhuis_configuration_is_upgraded_for_kassa")

        save_waar_inhuis_configuration(
            conn,
            household_id="waar-inhuis-household",
            unpacking_enabled=True,
            receipt_processing_enabled=True,
            almost_out_enabled=True,
        )
        waar_payload = _public_onboarding_with_product_configuration(
            conn,
            _state("waar-inhuis-household", "waar_inhuis"),
            can_manage=True,
        )
        waar_config = waar_payload["product_configuration"]
        assert waar_config["inventory_tracking_level"] == "presence"
        assert waar_config["location_tracking_level"] == "exact"
        assert waar_config["unpacking_enabled"] is True
        assert waar_config["receipt_processing_enabled"] is True
        checks.append("waar_inhuis_configuration_is_projected")

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("DYNAMIC_NAVIGATION_PRODUCT_PROJECTION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
