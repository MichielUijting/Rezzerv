"""Deterministic PostgreSQL proof for F6-01 Inventory controlled 5xx rollback."""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from p0_inventory_correction_fixture import (
    ARTICLE_ID,
    ARTICLE_NAME,
    HOUSEHOLD_ID,
    INITIAL_QUANTITY,
    INVENTORY_ID,
    TARGET_QUANTITY,
    prepare as prepare_inventory,
)
from app.services.f6_failure_injection import F6_SQL_FAILURE_SENTINEL
from app.testing.postgresql_onboarding_selftest_fixture import create_postgresql_runtime_test_engine


def prepare() -> dict:
    payload = prepare_inventory()
    payload["failure_note"] = F6_SQL_FAILURE_SENTINEL
    payload["initial_quantity"] = str(INITIAL_QUANTITY)
    payload["target_quantity"] = str(TARGET_QUANTITY)
    return payload


def verify_rollback() -> dict:
    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql", engine.dialect.name
        with engine.begin() as conn:
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
                {
                    "inventory_id": INVENTORY_ID,
                    "household_id": HOUSEHOLD_ID,
                    "article_id": ARTICLE_ID,
                },
            ).mappings().one()
            quantity = Decimal(str(inventory["quantity_text"]))
            assert quantity == INITIAL_QUANTITY, inventory

            sentinel_events = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM inventory_events
                    WHERE household_id = :household_id
                      AND household_article_id = :article_id
                      AND note = :note
                    """
                ),
                {
                    "household_id": HOUSEHOLD_ID,
                    "article_id": ARTICLE_ID,
                    "note": F6_SQL_FAILURE_SENTINEL,
                },
            ).scalar_one()
            assert int(sentinel_events) == 0, sentinel_events

            all_events = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM inventory_events
                    WHERE household_id = :household_id
                      AND household_article_id = :article_id
                    """
                ),
                {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID},
            ).scalar_one()
            assert int(all_events) == 0, all_events

        return {
            "household_id": HOUSEHOLD_ID,
            "article_id": ARTICLE_ID,
            "article_name": ARTICLE_NAME,
            "inventory_id": INVENTORY_ID,
            "quantity_after_failure": str(quantity),
            "sentinel_event_count": int(sentinel_events),
            "article_event_count": int(all_events),
        }
    finally:
        engine.dispose()


def main() -> int:
    mode = str(sys.argv[1] if len(sys.argv) > 1 else "prepare").strip().lower()
    if mode == "prepare":
        payload = prepare()
        print("F6_INVENTORY_FIXTURE=" + json.dumps(payload, default=str, sort_keys=True))
        print("F6_INVENTORY_FIXTURE_GREEN")
        return 0
    if mode == "verify":
        payload = verify_rollback()
        print("F6_INVENTORY_ROLLBACK_PROOF=" + json.dumps(payload, default=str, sort_keys=True))
        print("F6_INVENTORY_POSTGRESQL_ROLLBACK_GREEN")
        return 0
    raise SystemExit(f"Unsupported mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
