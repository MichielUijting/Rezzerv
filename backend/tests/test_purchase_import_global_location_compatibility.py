import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services.household_product_configuration_service import (
    ensure_household_product_configuration_foundation,
)
from app.services.inventory_location_household_patch import (
    normalize_persisted_purchase_import_target_location,
    validate_purchase_import_target_location_for_policy,
)
from app.services.inventory_location_policy_service import (
    resolve_inventory_target_location,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
    seed_household,
)


@pytest.fixture
def engine():
    reset_postgresql_test_database()
    test_engine = create_postgresql_runtime_test_engine()
    try:
        yield test_engine
    finally:
        test_engine.dispose()


def _seed_global_household(conn):
    ensure_household_product_configuration_foundation(conn)
    seed_household(
        conn,
        household_id="house-global",
        name="Globale locaties",
    )
    conn.execute(text("""
        INSERT INTO household_product_configuration (
            household_id,
            inventory_tracking_level,
            location_tracking_level,
            shopping_enabled,
            almost_out_enabled,
            almost_out_notifications_enabled,
            receipt_processing_enabled,
            recipes_enabled,
            unpacking_enabled
        ) VALUES (
            'house-global', 'presence', 'global', 0, 1, 0, 1, 0, 0
        )
    """))
    conn.execute(text("""
        INSERT INTO spaces (id, naam, household_id, active)
        VALUES ('berging', 'Berging', 'house-global', TRUE)
    """))
    conn.execute(text("""
        INSERT INTO sublocations (id, naam, space_id, active)
        VALUES ('voorraadkast', 'Voorraadkast', 'berging', TRUE)
    """))


def test_canonical_global_policy_still_rejects_sublocation_input(engine):
    with engine.begin() as conn:
        _seed_global_household(conn)
        with pytest.raises(HTTPException) as exc_info:
            resolve_inventory_target_location(
                conn,
                "house-global",
                "voorraadkast",
            )
        assert exc_info.value.status_code == 404


def test_old_persisted_global_sublocation_is_normalized_to_parent_for_processing(engine):
    with engine.begin() as conn:
        _seed_global_household(conn)
        resolved = normalize_persisted_purchase_import_target_location(
            conn,
            "house-global",
            "voorraadkast",
        )
        assert resolved is not None
        assert resolved["location_id"] == "berging"
        assert resolved["space_id"] == "berging"
        assert resolved["sublocation_id"] is None
        assert resolved["location_label"] == "Berging"


def test_new_global_sublocation_choice_is_rejected_with_parent_hint(engine):
    with engine.begin() as conn:
        _seed_global_household(conn)
        resolved, error = validate_purchase_import_target_location_for_policy(
            conn,
            "house-global",
            "voorraadkast",
        )
        assert resolved is None
        assert error is not None
        assert "alleen hoofdlocaties" in error
        assert "Berging" in error
        assert "Voorraadkast" in error


def test_new_global_main_space_choice_is_accepted(engine):
    with engine.begin() as conn:
        _seed_global_household(conn)
        resolved, error = validate_purchase_import_target_location_for_policy(
            conn,
            "house-global",
            "berging",
        )
        assert error is None
        assert resolved is not None
        assert resolved["location_id"] == "berging"
        assert resolved["space_id"] == "berging"
        assert resolved["sublocation_id"] is None
