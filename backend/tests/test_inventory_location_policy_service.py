import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.schemas.inventory import InventoryCreate
from app.services.household_product_configuration_service import (
    ensure_household_product_configuration_foundation,
)
from app.services.inventory_location_policy_service import (
    resolve_inventory_location,
    resolve_inventory_target_location,
)


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def _create_product_configuration_fixture(conn):
    conn.execute(text("""
        CREATE TABLE household_product_configuration (
            household_id TEXT PRIMARY KEY,
            inventory_tracking_level TEXT NOT NULL,
            location_tracking_level TEXT NOT NULL,
            shopping_enabled INTEGER NOT NULL DEFAULT 1,
            almost_out_enabled INTEGER NOT NULL DEFAULT 0,
            almost_out_notifications_enabled INTEGER NOT NULL DEFAULT 0,
            receipt_processing_enabled INTEGER NOT NULL DEFAULT 0,
            recipes_enabled INTEGER NOT NULL DEFAULT 0,
            unpacking_enabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    ensure_household_product_configuration_foundation(conn)


def _seed(conn):
    conn.execute(text("""
        CREATE TABLE spaces (
            id TEXT PRIMARY KEY,
            naam TEXT NOT NULL,
            household_id TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """))
    conn.execute(text("""
        CREATE TABLE sublocations (
            id TEXT PRIMARY KEY,
            naam TEXT NOT NULL,
            space_id TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """))
    _create_product_configuration_fixture(conn)

    for household_id, location_level in [
        ("house-none", "none"),
        ("house-global", "global"),
        ("house-exact", "exact"),
    ]:
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
                :household_id,
                'quantity',
                :location_level,
                1, 0, 0, 1, 0, 0
            )
        """), {
            "household_id": household_id,
            "location_level": location_level,
        })

    conn.execute(text("""
        INSERT INTO spaces (id, naam, household_id, active) VALUES
            ('none-space', 'Verboden ruimte', 'house-none', 1),
            ('global-space', 'Voorraadkast', 'house-global', 1),
            ('global-other', 'Andere kast', 'other-house', 1),
            ('exact-space', 'Keuken', 'house-exact', 1),
            ('exact-terminal', 'Garage', 'house-exact', 1)
    """))
    conn.execute(text("""
        INSERT INTO sublocations (id, naam, space_id, active) VALUES
            ('global-shelf', 'Plank', 'global-space', 1),
            ('exact-shelf', 'Bovenste plank', 'exact-space', 1)
    """))


def test_inventory_create_accepts_a_real_locationless_payload():
    payload = InventoryCreate(naam="Melk", aantal=2)
    assert payload.space_id is None
    assert payload.sublocation_id is None


def test_none_policy_returns_real_nulls_and_rejects_supplied_location():
    engine = _engine()
    with engine.begin() as conn:
        _seed(conn)
        resolved = resolve_inventory_location(conn, "house-none")
        assert resolved == {
            "location_id": None,
            "space_id": None,
            "sublocation_id": None,
            "location_label": "",
        }
        assert resolve_inventory_target_location(conn, "house-none", None) == resolved

        with pytest.raises(HTTPException) as exc_info:
            resolve_inventory_location(conn, "house-none", space_id="none-space")
        assert exc_info.value.status_code == 400
        assert "zonder locatie" in str(exc_info.value.detail)

        with pytest.raises(HTTPException) as exc_info:
            resolve_inventory_target_location(conn, "house-none", "none-space")
        assert exc_info.value.status_code == 400


def test_global_policy_requires_one_owned_main_space_and_rejects_sublocations():
    engine = _engine()
    with engine.begin() as conn:
        _seed(conn)
        resolved = resolve_inventory_location(
            conn,
            "house-global",
            space_id="global-space",
        )
        assert resolved["location_id"] == "global-space"
        assert resolved["space_id"] == "global-space"
        assert resolved["sublocation_id"] is None

        target_resolved = resolve_inventory_target_location(
            conn,
            "house-global",
            "global-space",
        )
        assert target_resolved == resolved

        with pytest.raises(HTTPException) as exc_info:
            resolve_inventory_location(conn, "house-global")
        assert exc_info.value.status_code == 400

        with pytest.raises(HTTPException) as exc_info:
            resolve_inventory_location(
                conn,
                "house-global",
                space_id="global-space",
                sublocation_id="global-shelf",
            )
        assert exc_info.value.status_code == 400

        with pytest.raises(HTTPException) as exc_info:
            resolve_inventory_target_location(conn, "house-global", "global-shelf")
        assert exc_info.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info:
            resolve_inventory_location(
                conn,
                "house-global",
                space_id="global-other",
            )
        assert exc_info.value.status_code == 404


def test_exact_policy_preserves_terminal_location_contract():
    engine = _engine()
    with engine.begin() as conn:
        _seed(conn)
        shelf = resolve_inventory_location(
            conn,
            "house-exact",
            sublocation_id="exact-shelf",
        )
        assert shelf["location_id"] == "exact-shelf"
        assert shelf["space_id"] == "exact-space"
        assert shelf["sublocation_id"] == "exact-shelf"

        target_shelf = resolve_inventory_target_location(
            conn,
            "house-exact",
            "exact-shelf",
        )
        assert target_shelf == shelf

        with pytest.raises(HTTPException) as exc_info:
            resolve_inventory_location(
                conn,
                "house-exact",
                space_id="exact-space",
            )
        assert exc_info.value.status_code == 400
        assert "Kies een sublocatie" in str(exc_info.value.detail)

        terminal = resolve_inventory_location(
            conn,
            "house-exact",
            space_id="exact-terminal",
        )
        assert terminal["location_id"] == "exact-terminal"
        assert terminal["sublocation_id"] is None
