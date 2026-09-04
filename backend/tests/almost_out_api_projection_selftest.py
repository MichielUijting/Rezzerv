"""P0 F3-05: Almost-out API projection authority on PostgreSQL.

This authority connects the already proven inventory/almost-out service chain to
what the user-facing backend actually exposes. It uses the canonical Fase-2
threshold cases, the production FastAPI route, real household authorization and
a DML-only PostgreSQL runtime. It verifies projection, recalculation,
household isolation and read idempotency without mocking business behavior.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.testing.canonical_scenario_catalog import load_canonical_scenario_catalog
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    seed_admin_member_household,
)

TARGET_HOUSEHOLD = "f3-almost-out-target"
ISOLATION_HOUSEHOLD = "f3-almost-out-isolation"
TARGET_ADMIN_EMAIL = "f3-almost-out-admin@rezzerv.local"
ISOLATION_ADMIN_EMAIL = "f3-almost-out-isolation-admin@rezzerv.local"
SEED_PASSWORD = "F3AlmostOutSeed123!"


def _headers(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer rezzerv-dev-token::{email.lower()}"}


def _prepare_database(engine) -> None:
    seed_admin_member_household(
        engine,
        household_id=TARGET_HOUSEHOLD,
        household_name="F3 Bijna-op doelhuishouden",
        admin_id="f3-almost-out-admin",
        admin_email=TARGET_ADMIN_EMAIL,
        admin_password=SEED_PASSWORD,
        admin_membership_id="f3-almost-out-admin-membership",
        member_id="f3-almost-out-member",
        member_email="f3-almost-out-member@rezzerv.local",
        member_password=SEED_PASSWORD,
        member_membership_id="f3-almost-out-member-membership",
    )
    seed_admin_member_household(
        engine,
        household_id=ISOLATION_HOUSEHOLD,
        household_name="F3 Bijna-op isolatiehuishouden",
        admin_id="f3-almost-out-isolation-admin",
        admin_email=ISOLATION_ADMIN_EMAIL,
        admin_password=SEED_PASSWORD,
        admin_membership_id="f3-almost-out-isolation-admin-membership",
        member_id="f3-almost-out-isolation-member",
        member_email="f3-almost-out-isolation-member@rezzerv.local",
        member_password=SEED_PASSWORD,
        member_membership_id="f3-almost-out-isolation-member-membership",
    )


def _seed_article(
    conn,
    *,
    household_id: str,
    article_id: str,
    inventory_id: str,
    name: str,
    quantity: Decimal,
    min_stock: Decimal,
    ideal_stock: Decimal,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO household_articles (
                id, household_id, naam, consumable, min_stock, ideal_stock, status, updated_at
            ) VALUES (
                :id, :household_id, :naam, 1, :min_stock, :ideal_stock, 'active', CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": article_id,
            "household_id": household_id,
            "naam": name,
            "min_stock": min_stock,
            "ideal_stock": ideal_stock,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO inventory (
                id, naam, aantal, household_id, household_article_id,
                space_id, sublocation_id, status, updated_at
            ) VALUES (
                :id, :naam, :aantal, :household_id, :household_article_id,
                NULL, NULL, 'active', CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": inventory_id,
            "naam": name,
            "aantal": quantity,
            "household_id": household_id,
            "household_article_id": article_id,
        },
    )


def _items_by_article_id(response) -> dict[str, dict]:
    assert response.status_code == 200, response.text
    payload = response.json()
    items = payload.get("items")
    assert isinstance(items, list), payload
    result: dict[str, dict] = {}
    for item in items:
        article_id = str(item.get("household_article_id") or "")
        assert article_id, item
        result[article_id] = item
    return result


def _decimal_field(item: dict, key: str) -> Decimal:
    value = item.get(key)
    assert value is not None, (key, item)
    return Decimal(str(value))


def run() -> int:
    checks: list[str] = []
    catalog = load_canonical_scenario_catalog()
    almost_out = catalog["almost_out_cases"]
    min_stock = Decimal(str(almost_out["min_stock"]))
    ideal_stock = min_stock + Decimal("3")

    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql"
        with engine.begin() as conn:
            assert bool(
                conn.execute(
                    text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                ).scalar_one()
            ) is False
        checks.append("postgresql_dml_only_runtime")

        _prepare_database(engine)

        article_ids: dict[str, str] = {}
        inventory_ids: dict[str, str] = {}
        with engine.begin() as conn:
            for case_name in ("above", "equal", "below", "zero"):
                case = almost_out[case_name]
                article_id = f"f3-almost-out-{case_name}"
                inventory_id = f"f3-almost-out-inventory-{case_name}"
                article_ids[case_name] = article_id
                inventory_ids[case_name] = inventory_id
                _seed_article(
                    conn,
                    household_id=TARGET_HOUSEHOLD,
                    article_id=article_id,
                    inventory_id=inventory_id,
                    name=f"F3 Bijna-op {case_name}",
                    quantity=Decimal(str(case["quantity"])),
                    min_stock=min_stock,
                    ideal_stock=ideal_stock,
                )

            _seed_article(
                conn,
                household_id=ISOLATION_HOUSEHOLD,
                article_id="f3-almost-out-foreign",
                inventory_id="f3-almost-out-inventory-foreign",
                name="F3 Bijna-op vreemd huishouden",
                quantity=Decimal("0"),
                min_stock=min_stock,
                ideal_stock=ideal_stock,
            )

        from app import main as main_module

        main_module.engine = engine
        with engine.begin() as conn:
            main_module.set_household_almost_out_settings(
                conn,
                TARGET_HOUSEHOLD,
                prediction_enabled=False,
                prediction_days=14,
                policy_mode=main_module.ALMOST_OUT_POLICY_ADVISORY,
            )
            main_module.set_household_almost_out_settings(
                conn,
                ISOLATION_HOUSEHOLD,
                prediction_enabled=False,
                prediction_days=14,
                policy_mode=main_module.ALMOST_OUT_POLICY_ADVISORY,
            )

        owner_headers = _headers(TARGET_ADMIN_EMAIL)
        isolation_headers = _headers(ISOLATION_ADMIN_EMAIL)
        target_url = f"/api/households/{TARGET_HOUSEHOLD}/almost-out"

        with TestClient(main_module.app) as client:
            initial = client.get(target_url, headers=owner_headers)
            initial_items = _items_by_article_id(initial)

            assert article_ids["above"] not in initial_items, initial_items
            for case_name in ("equal", "below", "zero"):
                article_id = article_ids[case_name]
                assert article_id in initial_items, (case_name, initial_items)
                item = initial_items[article_id]
                assert _decimal_field(item, "current_quantity") == Decimal(str(almost_out[case_name]["quantity"]))
                assert _decimal_field(item, "min_stock") == min_stock
                assert _decimal_field(item, "ideal_stock") == ideal_stock
                assert _decimal_field(item, "amount_to_buy") == ideal_stock - Decimal(str(almost_out[case_name]["quantity"]))
            assert "f3-almost-out-foreign" not in initial_items
            checks.append("canonical_threshold_cases_project_through_real_api")
            checks.append("locationless_inventory_projects_without_location_requirement")

            forbidden = client.get(target_url, headers=isolation_headers)
            assert forbidden.status_code == 403, forbidden.text

            own_isolation = client.get(
                f"/api/households/{ISOLATION_HOUSEHOLD}/almost-out",
                headers=isolation_headers,
            )
            isolation_items = _items_by_article_id(own_isolation)
            assert "f3-almost-out-foreign" in isolation_items
            assert not set(article_ids.values()).intersection(isolation_items)
            checks.append("cross_household_almost_out_read_is_blocked_and_isolated")

            with engine.begin() as conn:
                event_count_before = int(
                    conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar_one()
                )

            repeated = client.get(target_url, headers=owner_headers)
            repeated_items = _items_by_article_id(repeated)
            assert repeated_items == initial_items

            with engine.begin() as conn:
                event_count_after = int(
                    conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar_one()
                )
                assert event_count_after == event_count_before
            checks.append("repeated_projection_read_is_idempotent")

            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE inventory
                        SET aantal = :quantity, updated_at = CURRENT_TIMESTAMP
                        WHERE id = :inventory_id AND household_id = :household_id
                        """
                    ),
                    {
                        "quantity": Decimal(str(almost_out["above"]["quantity"])),
                        "inventory_id": inventory_ids["below"],
                        "household_id": TARGET_HOUSEHOLD,
                    },
                )

            after_restock = _items_by_article_id(client.get(target_url, headers=owner_headers))
            assert article_ids["below"] not in after_restock

            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE inventory
                        SET aantal = :quantity, updated_at = CURRENT_TIMESTAMP
                        WHERE id = :inventory_id AND household_id = :household_id
                        """
                    ),
                    {
                        "quantity": Decimal(str(almost_out["below"]["quantity"])),
                        "inventory_id": inventory_ids["below"],
                        "household_id": TARGET_HOUSEHOLD,
                    },
                )

            after_consume = _items_by_article_id(client.get(target_url, headers=owner_headers))
            assert article_ids["below"] in after_consume
            assert _decimal_field(after_consume[article_ids["below"]], "current_quantity") == Decimal(str(almost_out["below"]["quantity"]))
            checks.append("recalculation_disappears_above_threshold_and_reappears_below")

        with engine.begin() as conn:
            target_rows = conn.execute(
                text(
                    """
                    SELECT ha.id, ha.household_id, i.aantal
                    FROM household_articles ha
                    JOIN inventory i ON i.household_article_id = ha.id
                    WHERE ha.id = ANY(:article_ids)
                    ORDER BY ha.id
                    """
                ),
                {"article_ids": list(article_ids.values())},
            ).mappings().all()
            assert len(target_rows) == 4, target_rows
            assert all(str(row["household_id"]) == TARGET_HOUSEHOLD for row in target_rows)
            foreign_household = conn.execute(
                text("SELECT household_id FROM household_articles WHERE id = 'f3-almost-out-foreign'")
            ).scalar_one()
            assert str(foreign_household) == ISOLATION_HOUSEHOLD
        checks.append("postgresql_end_state_preserves_projection_source_and_household_isolation")

        for check in checks:
            print(f"PASS {check}")
        print(f"RESULT {len(checks)}/7 checks passed")
        assert len(checks) == 7
        print("ALMOST_OUT_API_PROJECTION_POSTGRESQL_GREEN")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run())
