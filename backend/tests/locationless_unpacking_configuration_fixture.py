"""Enable Uitpakken only for a fresh browser-created test household.

Run between browser onboarding and receipt upload in an isolated PostgreSQL
authority, preserving its explicitly expected none/global location policy.
No receipt, article or inventory state is seeded or processed here.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.household_capability_expansion_service import expand_household_product_configuration
from app.services.household_product_configuration_service import resolve_household_product_configuration
from app.testing.postgresql_acceptance_foundation import create_postgresql_runtime_test_engine


def main() -> None:
    household_id = os.environ["LOCATIONLESS_TEST_HOUSEHOLD_ID"].strip()
    location_level = os.environ.get("UNPACKING_TEST_LOCATION_LEVEL", "none").strip()
    assert location_level in {"none", "global"}, "Explicit supported location policy required"
    assert household_id and household_id != "0", "Dedicated browser household required"
    engine = create_postgresql_runtime_test_engine()
    try:
        with engine.begin() as conn:
            assert str(conn.execute(text("SELECT current_user")).scalar_one()) == "rezzerv_app"
            configuration = resolve_household_product_configuration(conn, household_id)
            assert configuration.inventory_tracking_level == "quantity"
            assert configuration.location_tracking_level == location_level
            assert configuration.unpacking_enabled is False
            for table in ("receipt_tables", "purchase_import_batches", "inventory_events"):
                assert conn.execute(text(
                    f"SELECT COUNT(*) FROM {table} WHERE household_id = :household_id"
                ), {"household_id": household_id}).scalar_one() == 0, table
            configuration = expand_household_product_configuration(
                conn, household_id=household_id, unpacking_enabled=True,
            )
            assert configuration.unpacking_enabled is True
            assert configuration.location_tracking_level == location_level
        print("LOCATIONLESS_UNPACKING_CONFIGURATION_GREEN")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
