from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from sqlalchemy import create_engine, text

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


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
HEAD_REVISION = "20260829_13"


def _migrated_sqlite_engine(database_path: Path):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    env["PYTHONPATH"] = str(BACKEND_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_INI),
            "upgrade",
            "head",
        ],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Alembic circular-capability fixture migration failed:\n"
            + result.stdout
            + result.stderr
        )
    engine = create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}", future=True)
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert revision == HEAD_REVISION
    return engine


def run() -> None:
    temp_dir = tempfile.TemporaryDirectory()
    engine = _migrated_sqlite_engine(Path(temp_dir.name) / "circular-capability.sqlite")
    with engine.begin() as conn:
        initial = save_inhuis_halen_configuration(
            conn,
            household_id="h1",
            simple_inventory_enabled=True,
            almost_out_notifications_enabled=True,
            receipt_processing_enabled=True,
            recipes_enabled=True,
        )
        assert initial.inventory_tracking_level == "quantity"
        assert initial.location_tracking_level == "none"
        assert initial.shopping_enabled is True
        assert initial.receipt_processing_enabled is True
        assert initial.recipes_enabled is True

        after_wat = expand_with_wat_inhuis(
            conn,
            household_id="h1",
            inventory_tracking_level="presence",
            global_locations_enabled=True,
            almost_out_enabled=False,
            shopping_enabled=False,
        )
        assert after_wat.inventory_tracking_level == "quantity", "quantity mag niet downgraden naar presence"
        assert after_wat.location_tracking_level == "global"
        assert after_wat.shopping_enabled is True
        assert after_wat.almost_out_enabled is True
        assert after_wat.almost_out_notifications_enabled is True
        assert after_wat.receipt_processing_enabled is True
        assert after_wat.recipes_enabled is True

        ensure_location_foundation(conn)
        conn.execute(text("INSERT INTO spaces (id, naam, household_id, active) VALUES ('s1', 'Keuken', 'h1', 1)"))
        provisioned = provision_waar_inhuis_expansion_locations(
            conn,
            household_id="h1",
            main_locations=["Garage"],
            sublocations=[{"space_name": "Keuken", "name": "Voorraadkast"}],
        )
        assert len(provisioned["spaces"]) == 1
        assert provisioned["spaces"][0]["name"] == "Garage"
        assert len(provisioned["sublocations"]) == 1
        assert provisioned["sublocations"][0]["space_name"] == "Keuken"
        assert conn.execute(text("SELECT COUNT(*) FROM spaces WHERE household_id='h1' AND naam='Keuken'")).scalar() == 1

        after_waar = expand_with_waar_inhuis(
            conn,
            household_id="h1",
            unpacking_enabled=True,
            receipt_processing_enabled=False,
            almost_out_enabled=False,
        )
        assert after_waar.inventory_tracking_level == "quantity"
        assert after_waar.location_tracking_level == "exact"
        assert after_waar.shopping_enabled is True
        assert after_waar.almost_out_notifications_enabled is True
        assert after_waar.receipt_processing_enabled is True
        assert after_waar.recipes_enabled is True
        assert after_waar.unpacking_enabled is True

        activate_household_product_use_case(conn, household_id="h1", use_case="wat_inhuis")
        activate_household_product_use_case(conn, household_id="h1", use_case="waar_inhuis")
        active = resolve_active_household_product_use_cases(
            conn,
            household_id="h1",
            primary_use_case="inhuis_halen",
        )
        assert active == ["inhuis_halen", "wat_inhuis", "waar_inhuis"]

        # Legacy/locationless voorraad blijft exact behouden wanneer Waar Inhuis later
        # wordt geactiveerd. Alleen de productpolicy wordt exact; historische voorraad
        # krijgt niet stilzwijgend een fictieve locatie en verliest geen aantallen.
        locationless_initial = save_inhuis_halen_configuration(
            conn,
            household_id="h-locationless",
            simple_inventory_enabled=True,
            almost_out_notifications_enabled=False,
            receipt_processing_enabled=False,
            recipes_enabled=False,
        )
        assert locationless_initial.location_tracking_level == "none"
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS inventory (
                id TEXT PRIMARY KEY,
                naam TEXT,
                aantal INTEGER,
                household_id TEXT,
                household_article_id TEXT,
                space_id TEXT,
                sublocation_id TEXT,
                status TEXT,
                updated_at TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO inventory (
                id, naam, aantal, household_id, household_article_id,
                space_id, sublocation_id, status, updated_at
            ) VALUES (
                'inv-locationless', 'Pasta', 5, 'h-locationless', 'article-pasta',
                NULL, NULL, 'active', CURRENT_TIMESTAMP
            )
        """))

        locationless_after_waar = expand_with_waar_inhuis(
            conn,
            household_id="h-locationless",
            unpacking_enabled=False,
            receipt_processing_enabled=False,
            almost_out_enabled=False,
        )
        assert locationless_after_waar.inventory_tracking_level == "quantity"
        assert locationless_after_waar.location_tracking_level == "exact"
        preserved = conn.execute(text("""
            SELECT aantal, space_id, sublocation_id, status
            FROM inventory
            WHERE id = 'inv-locationless'
        """)).mappings().one()
        assert int(preserved["aantal"]) == 5
        assert preserved["space_id"] is None
        assert preserved["sublocation_id"] is None
        assert preserved["status"] == "active"

        # Legacy household: viewing would create nothing; explicit expansion may create a neutral config.
        legacy = expand_with_wat_inhuis(
            conn,
            household_id="legacy",
            inventory_tracking_level="presence",
            global_locations_enabled=False,
            almost_out_enabled=False,
            shopping_enabled=False,
        )
        assert legacy.inventory_tracking_level == "presence"
        assert legacy.location_tracking_level == "none"
        assert legacy.shopping_enabled is False

    engine.dispose()
    temp_dir.cleanup()
    print("CIRCULAR_CAPABILITY_EXPANSION_BACKEND_GREEN")


if __name__ == "__main__":
    run()
