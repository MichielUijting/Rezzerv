"""Direct PostgreSQL verification for F6-04 interruption and safe-resume phases."""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.services.f6_failure_injection import F6_SQL_FAILURE_SENTINEL
from app.services.household_product_use_case_service import resolve_active_household_product_use_cases
from app.testing.postgresql_onboarding_selftest_fixture import create_postgresql_runtime_test_engine
from p0_inventory_correction_fixture import (
    ARTICLE_ID,
    HOUSEHOLD_ID as INVENTORY_HOUSEHOLD_ID,
    INVENTORY_ID,
    INITIAL_QUANTITY,
    TARGET_QUANTITY,
)


def _household_for_email(conn, email: str) -> str:
    row = conn.execute(
        text(
            """
            SELECT hm.household_id
            FROM household_memberships hm
            WHERE lower(trim(hm.user_email)) = :email
            ORDER BY hm.household_id
            """
        ),
        {"email": email.strip().lower()},
    ).mappings().all()
    assert len(row) == 1, row
    return str(row[0]["household_id"])


def _onboarding(conn, household_id: str):
    return conn.execute(
        text(
            """
            SELECT onboarding_status, primary_use_case, onboarding_step,
                   household_usage_mode, onboarding_completed_at
            FROM household_onboarding
            WHERE household_id = :household_id
            """
        ),
        {"household_id": household_id},
    ).mappings().one()


def _configuration(conn, household_id: str):
    return conn.execute(
        text(
            """
            SELECT inventory_tracking_level, location_tracking_level,
                   shopping_enabled, almost_out_enabled,
                   almost_out_notifications_enabled, receipt_processing_enabled,
                   recipes_enabled, unpacking_enabled
            FROM household_product_configuration
            WHERE household_id = :household_id
            """
        ),
        {"household_id": household_id},
    ).mappings().first()


def verify_onboarding_rollback(conn) -> dict:
    email = os.environ["F6_04_ONBOARDING_EMAIL"].strip().lower()
    household_id = _household_for_email(conn, email)
    onboarding = _onboarding(conn, household_id)
    config = _configuration(conn, household_id)
    assert onboarding["onboarding_status"] == "in_progress", onboarding
    assert onboarding["primary_use_case"] == "wat_inhuis", onboarding
    assert onboarding["onboarding_step"] == "profile_follow_up", onboarding
    assert onboarding["household_usage_mode"] is None, onboarding
    assert onboarding["onboarding_completed_at"] is None, onboarding
    assert config is None, config
    return {"email": email, "household_id": household_id, "step": "profile_follow_up", "configuration_rows": 0}


def verify_onboarding_success(conn) -> dict:
    email = os.environ["F6_04_ONBOARDING_EMAIL"].strip().lower()
    household_id = _household_for_email(conn, email)
    onboarding = _onboarding(conn, household_id)
    config = _configuration(conn, household_id)
    assert onboarding["onboarding_status"] == "in_progress", onboarding
    assert onboarding["primary_use_case"] == "wat_inhuis", onboarding
    assert onboarding["onboarding_step"] == "shared_household_minimum", onboarding
    assert config is not None, config
    assert config["inventory_tracking_level"] == "quantity", config
    assert config["location_tracking_level"] == "none", config
    assert bool(config["shopping_enabled"]) is True, config
    assert bool(config["almost_out_enabled"]) is True, config
    additional = conn.execute(
        text("SELECT COUNT(*) FROM household_product_use_cases WHERE household_id = :household_id"),
        {"household_id": household_id},
    ).scalar_one()
    assert int(additional) == 0, additional
    return {"email": email, "household_id": household_id, "step": "shared_household_minimum", "configuration_rows": 1}


def verify_settings_rollback(conn) -> dict:
    email = os.environ["F6_04_SETTINGS_EMAIL"].strip().lower()
    household_id = _household_for_email(conn, email)
    onboarding = _onboarding(conn, household_id)
    config = _configuration(conn, household_id)
    assert onboarding["onboarding_status"] == "completed", onboarding
    assert onboarding["primary_use_case"] == "inhuis_halen", onboarding
    assert config is not None, config
    assert config["inventory_tracking_level"] == "quantity", config
    assert config["location_tracking_level"] == "none", config
    assert bool(config["shopping_enabled"]) is True, config
    assert bool(config["almost_out_enabled"]) is True, config
    wat_rows = conn.execute(
        text(
            "SELECT COUNT(*) FROM household_product_use_cases "
            "WHERE household_id = :household_id AND use_case = 'wat_inhuis'"
        ),
        {"household_id": household_id},
    ).scalar_one()
    assert int(wat_rows) == 0, wat_rows
    active = resolve_active_household_product_use_cases(
        conn,
        household_id=household_id,
        primary_use_case="inhuis_halen",
    )
    assert active == ["inhuis_halen"], active
    spaces = conn.execute(
        text("SELECT COUNT(*) FROM spaces WHERE household_id = :household_id"),
        {"household_id": household_id},
    ).scalar_one()
    assert int(spaces) == 0, spaces
    return {"email": email, "household_id": household_id, "active_use_cases": active, "spaces": int(spaces)}


def verify_settings_success(conn) -> dict:
    email = os.environ["F6_04_SETTINGS_EMAIL"].strip().lower()
    household_id = _household_for_email(conn, email)
    onboarding = _onboarding(conn, household_id)
    config = _configuration(conn, household_id)
    assert onboarding["onboarding_status"] == "completed", onboarding
    assert onboarding["primary_use_case"] == "inhuis_halen", onboarding
    assert config is not None, config
    assert config["inventory_tracking_level"] == "quantity", config
    assert config["location_tracking_level"] == "global", config
    assert bool(config["shopping_enabled"]) is True, config
    assert bool(config["almost_out_enabled"]) is True, config
    wat_rows = conn.execute(
        text(
            "SELECT COUNT(*) FROM household_product_use_cases "
            "WHERE household_id = :household_id AND use_case = 'wat_inhuis'"
        ),
        {"household_id": household_id},
    ).scalar_one()
    assert int(wat_rows) == 1, wat_rows
    active = resolve_active_household_product_use_cases(
        conn,
        household_id=household_id,
        primary_use_case="inhuis_halen",
    )
    assert active == ["inhuis_halen", "wat_inhuis"], active
    return {"email": email, "household_id": household_id, "active_use_cases": active, "wat_rows": int(wat_rows)}


def verify_inventory_rollback(conn) -> dict:
    inventory = conn.execute(
        text(
            """
            SELECT aantal::text AS quantity_text
            FROM inventory
            WHERE id = :inventory_id
              AND household_id = :household_id
              AND household_article_id = :article_id
            """
        ),
        {"inventory_id": INVENTORY_ID, "household_id": INVENTORY_HOUSEHOLD_ID, "article_id": ARTICLE_ID},
    ).mappings().one()
    quantity = Decimal(str(inventory["quantity_text"]))
    assert quantity == INITIAL_QUANTITY, inventory
    sentinel_events = conn.execute(
        text(
            "SELECT COUNT(*) FROM inventory_events "
            "WHERE household_id = :household_id AND household_article_id = :article_id AND note = :note"
        ),
        {"household_id": INVENTORY_HOUSEHOLD_ID, "article_id": ARTICLE_ID, "note": F6_SQL_FAILURE_SENTINEL},
    ).scalar_one()
    assert int(sentinel_events) == 0, sentinel_events
    return {"quantity": str(quantity), "sentinel_events": 0}


def verify_inventory_success(conn) -> dict:
    inventory = conn.execute(
        text(
            """
            SELECT aantal::text AS quantity_text
            FROM inventory
            WHERE id = :inventory_id
              AND household_id = :household_id
              AND household_article_id = :article_id
            """
        ),
        {"inventory_id": INVENTORY_ID, "household_id": INVENTORY_HOUSEHOLD_ID, "article_id": ARTICLE_ID},
    ).mappings().one()
    quantity = Decimal(str(inventory["quantity_text"]))
    assert quantity == TARGET_QUANTITY, inventory
    sentinel_events = conn.execute(
        text(
            "SELECT COUNT(*) FROM inventory_events "
            "WHERE household_id = :household_id AND household_article_id = :article_id AND note = :note"
        ),
        {"household_id": INVENTORY_HOUSEHOLD_ID, "article_id": ARTICLE_ID, "note": F6_SQL_FAILURE_SENTINEL},
    ).scalar_one()
    all_events = conn.execute(
        text(
            "SELECT COUNT(*) FROM inventory_events "
            "WHERE household_id = :household_id AND household_article_id = :article_id"
        ),
        {"household_id": INVENTORY_HOUSEHOLD_ID, "article_id": ARTICLE_ID},
    ).scalar_one()
    assert int(sentinel_events) == 1, sentinel_events
    assert int(all_events) == 1, all_events
    return {"quantity": str(quantity), "sentinel_events": 1, "article_events": 1}


VERIFY = {
    "onboarding_rollback": verify_onboarding_rollback,
    "onboarding_success": verify_onboarding_success,
    "settings_rollback": verify_settings_rollback,
    "settings_success": verify_settings_success,
    "inventory_rollback": verify_inventory_rollback,
    "inventory_success": verify_inventory_success,
}


def main() -> int:
    mode = str(sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode not in VERIFY:
        raise SystemExit(f"Unsupported F6-04 verify mode: {mode}")
    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql", engine.dialect.name
        with engine.begin() as conn:
            proof = VERIFY[mode](conn)
    finally:
        engine.dispose()
    print("F6_04_PROOF=" + json.dumps({"mode": mode, **proof}, default=str, sort_keys=True))
    print(f"F6_04_{mode.upper()}_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
