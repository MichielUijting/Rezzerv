"""Deterministic PostgreSQL fixture for the P0 Almost-out recalculation authority.

The fixture seeds an already-existing chronological inventory history whose current
projection is 1. The browser must then insert a real manual stock correction with
an earlier effective timestamp than the seeded future history. Production replay
must keep the existing event identities, rewrite their balances, project stock to
4, and therefore remove the article from Bijna op.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
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

HOUSEHOLD_ID = "p0-almost-out-recalculation-household"
HOUSEHOLD_NAME = "P0 Bijna-op herberekening huishouden"
ADMIN_ID = "p0-almost-out-recalculation-admin"
ADMIN_EMAIL = "p0-almost-out-recalculation-admin@rezzerv.local"
ADMIN_PASSWORD = "P0AlmostOutSeed123!"
ADMIN_MEMBERSHIP_ID = "p0-almost-out-recalculation-admin-membership"
MEMBER_ID = "p0-almost-out-recalculation-member"
MEMBER_EMAIL = "p0-almost-out-recalculation-member@rezzerv.local"
MEMBER_MEMBERSHIP_ID = "p0-almost-out-recalculation-member-membership"
ARTICLE_ID = "p0-almost-out-recalculation-article"
ARTICLE_NAME = "P0 Historische Herberekening"
SPACE_ID = "p0-almost-out-recalculation-space"
SPACE_NAME = "P0 Historische Voorraadlocatie"
INVENTORY_ID = "p0-almost-out-recalculation-inventory"
PURCHASE_EVENT_ID = "p0-almost-out-existing-purchase"
CONSUME_EVENT_ID = "p0-almost-out-existing-consume"
INITIAL_QUANTITY = Decimal("1")
TARGET_QUANTITY = Decimal("4")
MIN_STOCK = Decimal("2")
IDEAL_STOCK = Decimal("4")
CORRECTION_DELTA = TARGET_QUANTITY - INITIAL_QUANTITY
CORRECTION_NOTE = "P0 Bijna-op historische herberekening"
EXISTING_PURCHASE_NOTE = "P0 bestaande historie aankoop"
EXISTING_CONSUME_NOTE = "P0 bestaande historie afboeking"


def _future_times() -> tuple[datetime, datetime]:
    base = datetime.now(timezone.utc) + timedelta(days=2)
    return base, base + timedelta(hours=1)


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

        purchase_at, consume_at = _future_times()
        recorded_at = datetime.now(timezone.utc)

        with engine.begin() as conn:
            current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
            runtime_create = bool(
                conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()
            )
            alembic_head = str(conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one())
            assert current_user == "rezzerv_app", current_user
            assert runtime_create is False
            assert alembic_head

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
                    INSERT INTO household_articles (id, household_id, naam, consumable, status, updated_at)
                    VALUES (:id, :household_id, :name, 1, 'active', CURRENT_TIMESTAMP)
                    """
                ),
                {"id": ARTICLE_ID, "household_id": HOUSEHOLD_ID, "name": ARTICLE_NAME},
            )
            conn.execute(
                text("INSERT INTO spaces (id, naam, household_id) VALUES (:id, :name, :household_id)"),
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
                    "quantity": str(INITIAL_QUANTITY),
                    "household_id": HOUSEHOLD_ID,
                    "article_id": ARTICLE_ID,
                    "space_id": SPACE_ID,
                },
            )

            common = {
                "household_id": HOUSEHOLD_ID,
                "article_id": ARTICLE_ID,
                "article_name": ARTICLE_NAME,
                "location_id": SPACE_ID,
                "location_label": SPACE_NAME,
                "recorded_at": recorded_at,
            }
            conn.execute(
                text(
                    """
                    INSERT INTO inventory_events (
                        id, household_id, article_id, household_article_id, article_name,
                        location_id, location_label, event_type, quantity,
                        old_quantity, new_quantity, source, note,
                        effective_at, recorded_at, effective_at_precision, event_priority,
                        source_reference, source_line_id, replayed_at, created_at
                    ) VALUES (
                        :id, :household_id, :article_id, :article_id, :article_name,
                        :location_id, :location_label, 'purchase', :quantity,
                        :old_quantity, :new_quantity, 'p0_fixture', :note,
                        :effective_at, :recorded_at, 'datetime', 10,
                        :source_reference, :source_line_id, :recorded_at, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    **common,
                    "id": PURCHASE_EVENT_ID,
                    "quantity": "3",
                    "old_quantity": "0",
                    "new_quantity": "3",
                    "note": EXISTING_PURCHASE_NOTE,
                    "effective_at": purchase_at,
                    "source_reference": "p0-almost-out-existing-history",
                    "source_line_id": "purchase",
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO inventory_events (
                        id, household_id, article_id, household_article_id, article_name,
                        location_id, location_label, event_type, quantity,
                        old_quantity, new_quantity, source, note,
                        effective_at, recorded_at, effective_at_precision, event_priority,
                        source_reference, source_line_id, replayed_at, created_at
                    ) VALUES (
                        :id, :household_id, :article_id, :article_id, :article_name,
                        :location_id, :location_label, 'consume', :quantity,
                        :old_quantity, :new_quantity, 'p0_fixture', :note,
                        :effective_at, :recorded_at, 'datetime', 40,
                        :source_reference, :source_line_id, :recorded_at, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    **common,
                    "id": CONSUME_EVENT_ID,
                    "quantity": "2",
                    "old_quantity": "3",
                    "new_quantity": "1",
                    "note": EXISTING_CONSUME_NOTE,
                    "effective_at": consume_at,
                    "source_reference": "p0-almost-out-existing-history",
                    "source_line_id": "consume",
                },
            )

            rows = conn.execute(
                text(
                    """
                    SELECT id, event_type, quantity::text AS quantity_text,
                           old_quantity::text AS old_quantity_text,
                           new_quantity::text AS new_quantity_text, effective_at
                    FROM inventory_events
                    WHERE household_id = :household_id AND household_article_id = :article_id
                    ORDER BY effective_at ASC, event_priority ASC, id ASC
                    """
                ),
                {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID},
            ).mappings().all()
            assert [str(row["id"]) for row in rows] == [PURCHASE_EVENT_ID, CONSUME_EVENT_ID], rows
            assert [Decimal(str(row["new_quantity_text"])) for row in rows] == [Decimal("3"), Decimal("1")], rows

        return {
            "household_id": HOUSEHOLD_ID,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "article_id": ARTICLE_ID,
            "article_name": ARTICLE_NAME,
            "inventory_id": INVENTORY_ID,
            "space_id": SPACE_ID,
            "initial_quantity": str(INITIAL_QUANTITY),
            "target_quantity": str(TARGET_QUANTITY),
            "min_stock": str(MIN_STOCK),
            "ideal_stock": str(IDEAL_STOCK),
            "note": CORRECTION_NOTE,
            "purchase_event_id": PURCHASE_EVENT_ID,
            "consume_event_id": CONSUME_EVENT_ID,
            "alembic_head": alembic_head,
        }
    finally:
        engine.dispose()


def verify() -> dict:
    expected_article = str(os.getenv("P0_ALMOST_OUT_ARTICLE_ID") or ARTICLE_ID).strip()
    expected_inventory = str(os.getenv("P0_ALMOST_OUT_INVENTORY_ID") or INVENTORY_ID).strip()
    assert expected_article == ARTICLE_ID, expected_article
    assert expected_inventory == INVENTORY_ID, expected_inventory

    engine = create_postgresql_runtime_test_engine()
    try:
        with engine.begin() as conn:
            current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
            runtime_create = bool(
                conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()
            )
            assert current_user == "rezzerv_app", current_user
            assert runtime_create is False

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
                {"inventory_id": INVENTORY_ID, "household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID},
            ).mappings().one()
            final_quantity = Decimal(str(inventory["quantity_text"]))
            assert final_quantity == TARGET_QUANTITY, inventory

            rows = conn.execute(
                text(
                    """
                    SELECT id, event_type, quantity::text AS quantity_text,
                           old_quantity::text AS old_quantity_text,
                           new_quantity::text AS new_quantity_text,
                           source, note, effective_at, replayed_at
                    FROM inventory_events
                    WHERE household_id = :household_id
                      AND household_article_id = :article_id
                    ORDER BY effective_at ASC, event_priority ASC,
                             COALESCE(source_reference, '') ASC,
                             COALESCE(source_line_id, '') ASC, id ASC
                    """
                ),
                {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID},
            ).mappings().all()
            assert len(rows) == 3, rows
            correction = next(row for row in rows if str(row["note"] or "") == CORRECTION_NOTE)
            purchase = next(row for row in rows if str(row["id"]) == PURCHASE_EVENT_ID)
            consume = next(row for row in rows if str(row["id"]) == CONSUME_EVENT_ID)

            assert rows[0]["id"] == correction["id"], rows
            assert str(correction["event_type"]) == "manual_adjustment", correction
            assert str(correction["source"]) == "manual_inventory_api", correction
            assert Decimal(str(correction["quantity_text"])) == CORRECTION_DELTA, correction
            assert Decimal(str(correction["old_quantity_text"])) == Decimal("0"), correction
            assert Decimal(str(correction["new_quantity_text"])) == Decimal("3"), correction

            assert Decimal(str(purchase["old_quantity_text"])) == Decimal("3"), purchase
            assert Decimal(str(purchase["new_quantity_text"])) == Decimal("6"), purchase
            assert Decimal(str(consume["old_quantity_text"])) == Decimal("6"), consume
            assert Decimal(str(consume["new_quantity_text"])) == TARGET_QUANTITY, consume
            assert purchase["replayed_at"] is not None, purchase
            assert consume["replayed_at"] is not None, consume

        return {
            "article_id": ARTICLE_ID,
            "inventory_id": INVENTORY_ID,
            "final_quantity": str(final_quantity),
            "correction_event_id": str(correction["id"]),
            "correction_delta": str(correction["quantity_text"]),
            "purchase_event_id": str(purchase["id"]),
            "purchase_old": str(purchase["old_quantity_text"]),
            "purchase_new": str(purchase["new_quantity_text"]),
            "consume_event_id": str(consume["id"]),
            "consume_old": str(consume["old_quantity_text"]),
            "consume_new": str(consume["new_quantity_text"]),
        }
    finally:
        engine.dispose()


def main() -> int:
    mode = str(sys.argv[1] if len(sys.argv) > 1 else "prepare").strip().lower()
    if mode == "prepare":
        payload = prepare()
        print("P0_ALMOST_OUT_FIXTURE=" + json.dumps(payload, default=str, sort_keys=True))
        print("P0_ALMOST_OUT_FIXTURE_GREEN")
        return 0
    if mode == "verify":
        payload = verify()
        print("P0_ALMOST_OUT_POSTGRESQL_PROOF=" + json.dumps(payload, default=str, sort_keys=True))
        print("P0_ALMOST_OUT_RECALCULATION_POSTGRESQL_GREEN")
        return 0
    raise SystemExit(f"Unsupported mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
