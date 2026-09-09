"""Deterministic PostgreSQL fixture for the P0 Inventory correction authority.

Only pre-user state is seeded. The correction itself must be performed through
the visible Article -> Voorraad browser UI. Final proof reads PostgreSQL using
stable household/article/inventory identities and an exact non-financial decimal.
"""
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

from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    seed_admin_member_household,
)

HOUSEHOLD_ID = "p0-inventory-household"
HOUSEHOLD_NAME = "P0 Inventory huishouden"
ADMIN_ID = "p0-inventory-admin"
ADMIN_EMAIL = "p0-inventory-admin@rezzerv.local"
ADMIN_PASSWORD = "P0InventorySeed123!"
ADMIN_MEMBERSHIP_ID = "p0-inventory-admin-membership"
MEMBER_ID = "p0-inventory-member"
MEMBER_EMAIL = "p0-inventory-member@rezzerv.local"
MEMBER_MEMBERSHIP_ID = "p0-inventory-member-membership"
ARTICLE_ID = "p0-inventory-exact-decimal-article"
ARTICLE_NAME = "P0 Exacte Decimaal"
SPACE_ID = "p0-inventory-exact-decimal-space"
SPACE_NAME = "P0 Voorraadlocatie"
INVENTORY_ID = "p0-inventory-exact-decimal-row"
INITIAL_QUANTITY = Decimal("2")
TARGET_QUANTITY = Decimal("1.234567")
EXPECTED_DELTA = TARGET_QUANTITY - INITIAL_QUANTITY
NOTE = "P0 exacte decimaal correctie 1.234567"


def prepare() -> dict:
    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql", engine.dialect.name
        seed_admin_member_household(
            engine,
            household_id=HOUSEHOLD_ID,
            household_name=HOUSEHOLD_NAME,
            admin_id=ADMIN_ID,
            admin_email=ADMIN_EMAIL,
            admin_password=ADMIN_PASSWORD,
            admin_membership_id=ADMIN_MEMBERSHIP_ID,
            member_id=MEMBER_ID,
            member_email=MEMBER_EMAIL,
            member_password=ADMIN_PASSWORD,
            member_membership_id=MEMBER_MEMBERSHIP_ID,
        )

        with engine.begin() as conn:
            current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
            runtime_create = bool(
                conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()
            )
            assert current_user == "rezzerv_app", current_user
            assert runtime_create is False

            conn.execute(
                text("DELETE FROM inventory_events WHERE household_id = :household_id AND (household_article_id = :article_id OR article_id = :article_id)"),
                {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID},
            )
            conn.execute(
                text("DELETE FROM inventory WHERE household_id = :household_id AND id = :inventory_id"),
                {"household_id": HOUSEHOLD_ID, "inventory_id": INVENTORY_ID},
            )
            conn.execute(
                text("DELETE FROM spaces WHERE household_id = :household_id AND id = :space_id"),
                {"household_id": HOUSEHOLD_ID, "space_id": SPACE_ID},
            )
            conn.execute(
                text("DELETE FROM household_articles WHERE household_id = :household_id AND id = :article_id"),
                {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID},
            )

            conn.execute(
                text(
                    """
                    INSERT INTO household_articles (
                        id, household_id, naam, consumable, status, updated_at
                    ) VALUES (
                        :id, :household_id, :name, 0, 'active', CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"id": ARTICLE_ID, "household_id": HOUSEHOLD_ID, "name": ARTICLE_NAME},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO spaces (id, naam, household_id)
                    VALUES (:id, :name, :household_id)
                    """
                ),
                {"id": SPACE_ID, "name": SPACE_NAME, "household_id": HOUSEHOLD_ID},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO inventory (
                        id, naam, aantal, household_id, household_article_id,
                        space_id, sublocation_id, status, updated_at
                    ) VALUES (
                        :id, :name, :quantity, :household_id, :article_id,
                        :space_id, NULL, 'active', CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": INVENTORY_ID,
                    "name": ARTICLE_NAME,
                    "quantity": INITIAL_QUANTITY,
                    "household_id": HOUSEHOLD_ID,
                    "article_id": ARTICLE_ID,
                    "space_id": SPACE_ID,
                },
            )

            start = conn.execute(
                text(
                    """
                    SELECT aantal, aantal::text AS quantity_text, space_id, sublocation_id
                    FROM inventory
                    WHERE id = :inventory_id AND household_id = :household_id
                    """
                ),
                {"inventory_id": INVENTORY_ID, "household_id": HOUSEHOLD_ID},
            ).mappings().one()
            assert Decimal(str(start["aantal"])) == INITIAL_QUANTITY, start
            assert str(start["space_id"] or "") == SPACE_ID, start
            assert start["sublocation_id"] is None, start

        return {
            "household_id": HOUSEHOLD_ID,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "article_id": ARTICLE_ID,
            "article_name": ARTICLE_NAME,
            "space_id": SPACE_ID,
            "space_name": SPACE_NAME,
            "inventory_id": INVENTORY_ID,
            "initial_quantity": str(INITIAL_QUANTITY),
            "target_quantity": str(TARGET_QUANTITY),
            "note": NOTE,
        }
    finally:
        engine.dispose()


def verify() -> dict:
    expected_article = str(os.getenv("P0_INVENTORY_ARTICLE_ID") or ARTICLE_ID).strip()
    expected_inventory = str(os.getenv("P0_INVENTORY_INVENTORY_ID") or INVENTORY_ID).strip()
    assert expected_article == ARTICLE_ID, expected_article
    assert expected_inventory == INVENTORY_ID, expected_inventory

    engine = create_postgresql_runtime_test_engine()
    try:
        with engine.begin() as conn:
            inventory = conn.execute(
                text(
                    """
                    SELECT aantal, aantal::text AS quantity_text, space_id, sublocation_id
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
            final_quantity = Decimal(str(inventory["quantity_text"]))
            assert final_quantity == TARGET_QUANTITY, inventory
            assert str(inventory["space_id"] or "") == SPACE_ID, inventory
            assert inventory["sublocation_id"] is None, inventory

            events = conn.execute(
                text(
                    """
                    SELECT id, event_type, quantity, quantity::text AS quantity_text,
                           old_quantity, old_quantity::text AS old_quantity_text,
                           new_quantity, new_quantity::text AS new_quantity_text,
                           source, note
                    FROM inventory_events
                    WHERE household_id = :household_id
                      AND household_article_id = :article_id
                      AND note = :note
                    ORDER BY created_at DESC NULLS LAST, id DESC
                    """
                ),
                {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID, "note": NOTE},
            ).mappings().all()
            assert len(events) == 1, events
            event = events[0]
            assert str(event["event_type"]) == "manual_adjustment", event
            assert str(event["source"]) == "manual_inventory_api", event
            assert Decimal(str(event["quantity_text"])) == EXPECTED_DELTA, event
            assert Decimal(str(event["old_quantity_text"])) == INITIAL_QUANTITY, event
            assert Decimal(str(event["new_quantity_text"])) == TARGET_QUANTITY, event

        return {
            "article_id": ARTICLE_ID,
            "space_id": SPACE_ID,
            "inventory_id": INVENTORY_ID,
            "final_quantity": str(final_quantity),
            "event_id": str(event["id"]),
            "event_quantity": str(event["quantity_text"]),
            "event_old_quantity": str(event["old_quantity_text"]),
            "event_new_quantity": str(event["new_quantity_text"]),
        }
    finally:
        engine.dispose()


def main() -> int:
    mode = str(sys.argv[1] if len(sys.argv) > 1 else "prepare").strip().lower()
    if mode == "prepare":
        payload = prepare()
        print("P0_INVENTORY_FIXTURE=" + json.dumps(payload, default=str, sort_keys=True))
        print("P0_INVENTORY_FIXTURE_GREEN")
        return 0
    if mode == "verify":
        payload = verify()
        print("P0_INVENTORY_POSTGRESQL_PROOF=" + json.dumps(payload, default=str, sort_keys=True))
        print("P0_INVENTORY_POSTGRESQL_GREEN")
        return 0
    raise SystemExit(f"Unsupported mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
