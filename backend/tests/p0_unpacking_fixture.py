"""Deterministic PostgreSQL fixture for the P0 Uitpakken browser authority.

Only the state that exists before a user processes an Uitpakken line is seeded.
The actual purchase-import processing mutation must be performed through the
visible browser UI. Final proof is read directly from PostgreSQL using stable IDs.
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

from app.services.day_article_service import (
    DIRECT_CONSUMPTION,
    ensure_direct_location,
    get_default_inventory_handling,
    set_default_inventory_handling,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    seed_admin_member_household,
)

HOUSEHOLD_ID = "p0-unpacking-household"
HOUSEHOLD_NAME = "P0 Uitpakken huishouden"
ADMIN_ID = "p0-unpacking-admin"
ADMIN_EMAIL = "p0-unpacking-admin@rezzerv.local"
ADMIN_PASSWORD = "P0UnpackingSeed123!"
ADMIN_MEMBERSHIP_ID = "p0-unpacking-admin-membership"
MEMBER_ID = "p0-unpacking-member"
MEMBER_EMAIL = "p0-unpacking-member@rezzerv.local"
MEMBER_MEMBERSHIP_ID = "p0-unpacking-member-membership"

ARTICLE_ID = "canonical-day-bananas"
PROVIDER_CODE = "p0-unpacking-provider"
PROVIDER_NAME = "P0 Uitpakken testwinkel"
BATCH_ID = "p0-unpacking-day-article-batch"
LINE_ID = "p0-unpacking-day-article-line"
INVENTORY_ID = "p0-unpacking-day-article-inventory"


def _canonical_day_article() -> dict:
    candidates = [
        Path("/quality/acceptance/canonical_scenario_catalog.json"),
        Path(__file__).resolve().parents[2] / "quality" / "acceptance" / "canonical_scenario_catalog.json",
    ]
    for path in candidates:
        if path.is_file():
            catalog = json.loads(path.read_text(encoding="utf-8"))
            article = dict(catalog["article_fixtures"]["day_article"])
            assert str(article["id"]) == ARTICLE_ID, article
            assert str(article["name"]) == "Bananen", article
            assert bool(article["consumable"]) is True, article
            assert Decimal(str(article["existing_quantity"])) == Decimal("3"), article
            assert Decimal(str(article["purchased_quantity"])) == Decimal("2"), article
            assert Decimal(str(article["expected_final_quantity"])) == Decimal("3"), article
            return article
    raise AssertionError("Canonical fixture ontbreekt: quality/acceptance/canonical_scenario_catalog.json")


def _seed_identity(engine) -> None:
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


def prepare() -> dict:
    canonical = _canonical_day_article()
    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql", engine.dialect.name
        _seed_identity(engine)

        with engine.begin() as conn:
            current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
            runtime_create = bool(
                conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()
            )
            assert current_user == "rezzerv_app", current_user
            assert runtime_create is False

            # Keep repeated fixture preparation deterministic without touching
            # state outside this dedicated synthetic household.
            conn.execute(
                text("DELETE FROM day_article_processing_events WHERE household_id = :household_id"),
                {"household_id": HOUSEHOLD_ID},
            )
            conn.execute(
                text("DELETE FROM purchase_import_lines WHERE batch_id = :batch_id"),
                {"batch_id": BATCH_ID},
            )
            conn.execute(
                text("DELETE FROM purchase_import_batches WHERE id = :batch_id"),
                {"batch_id": BATCH_ID},
            )
            conn.execute(
                text("DELETE FROM inventory WHERE household_id = :household_id AND household_article_id = :article_id"),
                {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID},
            )

            conn.execute(
                text(
                    """
                    INSERT INTO household_articles (
                        id, household_id, naam, consumable, status, updated_at
                    ) VALUES (
                        :id, :household_id, :name, 1, 'active', CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        household_id = EXCLUDED.household_id,
                        naam = EXCLUDED.naam,
                        consumable = 1,
                        status = 'active',
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "id": ARTICLE_ID,
                    "household_id": HOUSEHOLD_ID,
                    "name": canonical["name"],
                },
            )

            handling = set_default_inventory_handling(
                conn,
                household_id=HOUSEHOLD_ID,
                household_article_id=ARTICLE_ID,
                handling=DIRECT_CONSUMPTION,
                actor_user_id=ADMIN_ID,
            )
            assert handling["default_inventory_handling"] == DIRECT_CONSUMPTION, handling
            persisted_handling = get_default_inventory_handling(conn, HOUSEHOLD_ID, ARTICLE_ID)
            assert persisted_handling["default_inventory_handling"] == DIRECT_CONSUMPTION, persisted_handling

            direct = ensure_direct_location(conn, HOUSEHOLD_ID)
            direct_location_id = str(direct["sublocation_id"] or direct["space_id"])
            assert direct_location_id, direct
            assert str(direct["location"]) == "Direct", direct
            assert str(direct["sublocation"]) == "Direct", direct

            conn.execute(
                text(
                    """
                    INSERT INTO inventory (
                        id, naam, aantal, household_id, household_article_id,
                        space_id, sublocation_id, status, updated_at
                    ) VALUES (
                        :id, :name, :quantity, :household_id, :article_id,
                        NULL, NULL, 'active', CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": INVENTORY_ID,
                    "name": canonical["name"],
                    "quantity": int(Decimal(str(canonical["existing_quantity"]))),
                    "household_id": HOUSEHOLD_ID,
                    "article_id": ARTICLE_ID,
                },
            )

            provider_id = str(
                conn.execute(
                    text(
                        """
                        INSERT INTO store_providers (id, code, name, status, import_mode, created_at, updated_at)
                        VALUES (:id, :code, :name, 'active', 'mock', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON CONFLICT (code) DO UPDATE SET
                            name = EXCLUDED.name,
                            status = 'active',
                            import_mode = 'mock',
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id
                        """
                    ),
                    {"id": "p0-unpacking-provider-id", "code": PROVIDER_CODE, "name": PROVIDER_NAME},
                ).scalar_one()
            )

            connection_id = str(
                conn.execute(
                    text(
                        """
                        INSERT INTO household_store_connections (
                            id, household_id, store_provider_id, connection_status,
                            linked_at, created_at, updated_at
                        ) VALUES (
                            :id, :household_id, :provider_id, 'active',
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (household_id, store_provider_id) DO UPDATE SET
                            connection_status = 'active',
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id
                        """
                    ),
                    {
                        "id": "p0-unpacking-connection",
                        "household_id": HOUSEHOLD_ID,
                        "provider_id": provider_id,
                    },
                ).scalar_one()
            )

            conn.execute(
                text(
                    """
                    INSERT INTO purchase_import_batches (
                        id, household_id, store_provider_id, connection_id, source_type,
                        source_reference, import_status, raw_payload, created_at
                    ) VALUES (
                        :id, :household_id, :provider_id, :connection_id, 'mock',
                        :source_reference, 'in_review', :raw_payload, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": BATCH_ID,
                    "household_id": HOUSEHOLD_ID,
                    "provider_id": provider_id,
                    "connection_id": connection_id,
                    "source_reference": "p0-unpacking:canonical-day-bananas",
                    "raw_payload": json.dumps({
                        "fixture": "canonical-day-article",
                        "store_name": PROVIDER_NAME,
                        "purchase_date": "2026-09-08",
                    }),
                },
            )

            conn.execute(
                text(
                    """
                    INSERT INTO purchase_import_lines (
                        id, batch_id, external_line_ref, external_article_code,
                        article_name_raw, brand_raw, quantity_raw, unit_raw,
                        line_price_raw, currency_code, match_status, review_decision,
                        ui_sort_order, matched_household_article_id, target_location_id,
                        processing_status, suggested_household_article_id,
                        suggested_location_id, suggestion_confidence, suggestion_reason,
                        is_auto_prefilled, article_override_mode, location_override_mode,
                        created_at, updated_at
                    ) VALUES (
                        :id, :batch_id, 'canonical-day-bananas', 'CANONICAL-DAY-BANANAS',
                        :name, '', :quantity, 'stuks',
                        0.50, 'EUR', 'matched', 'selected',
                        1, :article_id, :target_location_id,
                        'pending', :article_id,
                        :target_location_id, 'high', 'Canonieke P0 dagartikel-fixture',
                        TRUE, 'auto', 'auto', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": LINE_ID,
                    "batch_id": BATCH_ID,
                    "name": canonical["name"],
                    "quantity": Decimal(str(canonical["purchased_quantity"])),
                    "article_id": ARTICLE_ID,
                    "target_location_id": direct_location_id,
                },
            )

            start_quantity = Decimal(
                str(
                    conn.execute(
                        text(
                            """
                            SELECT COALESCE(SUM(aantal), 0)
                            FROM inventory
                            WHERE household_id = :household_id
                              AND household_article_id = :article_id
                              AND COALESCE(status, 'active') = 'active'
                            """
                        ),
                        {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID},
                    ).scalar_one()
                )
            )
            assert start_quantity == Decimal(str(canonical["existing_quantity"])), start_quantity

        return {
            "household_id": HOUSEHOLD_ID,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "article_id": ARTICLE_ID,
            "article_name": canonical["name"],
            "batch_id": BATCH_ID,
            "line_id": LINE_ID,
            "direct_location_id": direct_location_id,
            "existing_quantity": str(canonical["existing_quantity"]),
            "purchased_quantity": str(canonical["purchased_quantity"]),
            "expected_final_quantity": str(canonical["expected_final_quantity"]),
        }
    finally:
        engine.dispose()


def verify() -> dict:
    expected_line_id = str(os.getenv("P0_UNPACKING_LINE_ID") or LINE_ID).strip()
    expected_batch_id = str(os.getenv("P0_UNPACKING_BATCH_ID") or BATCH_ID).strip()
    assert expected_line_id == LINE_ID, expected_line_id
    assert expected_batch_id == BATCH_ID, expected_batch_id
    canonical = _canonical_day_article()

    engine = create_postgresql_runtime_test_engine()
    try:
        with engine.begin() as conn:
            line = conn.execute(
                text(
                    """
                    SELECT id, batch_id, processing_status, processed_at, processed_event_id,
                           matched_household_article_id, target_location_id, quantity_raw
                    FROM purchase_import_lines
                    WHERE id = :line_id AND batch_id = :batch_id
                    """
                ),
                {"line_id": expected_line_id, "batch_id": expected_batch_id},
            ).mappings().one()
            assert str(line["processing_status"]) == "processed", line
            assert line["processed_at"] is not None, line
            assert str(line["processed_event_id"] or "").strip(), line
            assert str(line["matched_household_article_id"]) == ARTICLE_ID, line
            assert Decimal(str(line["quantity_raw"])) == Decimal(str(canonical["purchased_quantity"])), line

            events = conn.execute(
                text(
                    """
                    SELECT event_type, quantity, space_id, sublocation_id
                    FROM day_article_processing_events
                    WHERE household_id = :household_id
                      AND household_article_id = :article_id
                      AND idempotency_key = :idempotency_key
                    ORDER BY event_type
                    """
                ),
                {
                    "household_id": HOUSEHOLD_ID,
                    "article_id": ARTICLE_ID,
                    "idempotency_key": f"purchase-import-line:{LINE_ID}",
                },
            ).mappings().all()
            assert len(events) == 2, events
            assert {str(row["event_type"]) for row in events} == {"RECEIPT", "DIRECT_CONSUMPTION"}, events
            expected_purchase = Decimal(str(canonical["purchased_quantity"]))
            assert all(Decimal(str(row["quantity"])) == expected_purchase for row in events), events
            assert all(str(row["sublocation_id"] or row["space_id"] or "") == str(line["target_location_id"]) for row in events), (events, line)

            final_quantity = Decimal(
                str(
                    conn.execute(
                        text(
                            """
                            SELECT COALESCE(SUM(aantal), 0)
                            FROM inventory
                            WHERE household_id = :household_id
                              AND household_article_id = :article_id
                              AND COALESCE(status, 'active') = 'active'
                            """
                        ),
                        {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID},
                    ).scalar_one()
                )
            )
            assert final_quantity == Decimal(str(canonical["expected_final_quantity"])), final_quantity

            direct_inventory_rows = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM inventory i
                        JOIN spaces s ON s.id = i.space_id
                        LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
                        WHERE i.household_id = :household_id
                          AND i.household_article_id = :article_id
                          AND lower(COALESCE(s.naam, '')) = 'direct'
                          AND lower(COALESCE(sl.naam, 'direct')) = 'direct'
                          AND COALESCE(i.status, 'active') = 'active'
                        """
                    ),
                    {"household_id": HOUSEHOLD_ID, "article_id": ARTICLE_ID},
                ).scalar_one()
            )
            assert direct_inventory_rows == 0, direct_inventory_rows

        return {
            "batch_id": expected_batch_id,
            "line_id": expected_line_id,
            "article_id": ARTICLE_ID,
            "events": [dict(row) for row in events],
            "final_quantity": str(final_quantity),
            "direct_inventory_rows": direct_inventory_rows,
        }
    finally:
        engine.dispose()


def main() -> int:
    mode = str(sys.argv[1] if len(sys.argv) > 1 else "prepare").strip().lower()
    if mode == "prepare":
        payload = prepare()
        print("P0_UNPACKING_FIXTURE=" + json.dumps(payload, default=str, sort_keys=True))
        print("P0_UNPACKING_FIXTURE_GREEN")
        return 0
    if mode == "verify":
        payload = verify()
        print("P0_UNPACKING_POSTGRESQL_PROOF=" + json.dumps(payload, default=str, sort_keys=True))
        print("P0_UNPACKING_POSTGRESQL_GREEN")
        return 0
    raise SystemExit(f"Unsupported mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(main())
