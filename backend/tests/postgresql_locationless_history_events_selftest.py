from __future__ import annotations

from sqlalchemy import text

from app.db import engine
from app.services.household_product_configuration_service import save_wat_inhuis_configuration
from app.testing.postgresql_onboarding_selftest_fixture import seed_admin_member_household


HOUSEHOLD_ID = "f5-12-locationless-history-household"
ADMIN_ID = "f5-12-locationless-history-admin"
ADMIN_EMAIL = "f5-12-locationless-history-admin@rezzerv.local"
PASSWORD = "F5LocationlessHistory123!"
ARTICLE_ID = "f5-12-locationless-history-article"
ARTICLE_NAME = "F5-12 locatievrij historieartikel"
PURCHASE_EVENT_ID = "f5-12-locationless-purchase"
CONSUME_EVENT_ID = "f5-12-locationless-consume"
EXPECTED_EVENT_IDS = {PURCHASE_EVENT_ID, CONSUME_EVENT_ID}


def assert_locationless_history(rows: list[dict], label: str) -> None:
    relevant = [row for row in rows if str(row.get("id") or "") in EXPECTED_EVENT_IDS]
    actual_ids = {str(row.get("id") or "") for row in relevant}
    assert actual_ids == EXPECTED_EVENT_IDS, (
        f"{label}: Historie moet purchase en consume zonder locatie behouden; "
        f"expected={EXPECTED_EVENT_IDS} actual={actual_ids} rows={rows}"
    )
    for row in relevant:
        assert row.get("location_id") is None, (label, row)
        assert str(row.get("location_label") or "") == "", (label, row)


def main() -> int:
    assert engine.dialect.name == "postgresql", engine.dialect.name

    with engine.begin() as conn:
        current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
        runtime_create = bool(
            conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()
        )
    assert current_user == "rezzerv_app", current_user
    assert runtime_create is False
    print("PASS postgresql_runtime_is_dml_only")

    seed_admin_member_household(
        engine,
        household_id=HOUSEHOLD_ID,
        household_name="F5-12 locatievrije Historie",
        admin_id=ADMIN_ID,
        admin_email=ADMIN_EMAIL,
        admin_password=PASSWORD,
        admin_membership_id="f5-12-locationless-history-admin-membership",
        member_id="f5-12-locationless-history-member",
        member_email="f5-12-locationless-history-member@rezzerv.local",
        member_password=PASSWORD,
        member_membership_id="f5-12-locationless-history-member-membership",
    )

    from app import main as main_module

    main_module.engine = engine

    with engine.begin() as conn:
        configuration = save_wat_inhuis_configuration(
            conn,
            household_id=HOUSEHOLD_ID,
            inventory_tracking_level="quantity",
            global_locations_enabled=False,
            almost_out_enabled=True,
            shopping_enabled=True,
        )
        assert configuration.location_tracking_level == "none", configuration
        assert configuration.inventory_tracking_level == "quantity", configuration

        spaces_before = int(
            conn.execute(
                text("SELECT COUNT(*) FROM spaces WHERE household_id = :household_id"),
                {"household_id": HOUSEHOLD_ID},
            ).scalar_one()
        )
        assert spaces_before == 0, spaces_before

        conn.execute(
            text(
                """
                INSERT INTO household_articles (
                    id, household_id, naam, consumable, created_at, updated_at, source, status
                ) VALUES (
                    :id, :household_id, :naam, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                    'f5-12-regression', 'active'
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"id": ARTICLE_ID, "household_id": HOUSEHOLD_ID, "naam": ARTICLE_NAME},
        )

        events = (
            (PURCHASE_EVENT_ID, "purchase", 3, 0, 3, "locationless purchase"),
            (CONSUME_EVENT_ID, "consume", -1, 3, 2, "locationless consume"),
        )
        for event_id, event_type, quantity, old_quantity, new_quantity, note in events:
            conn.execute(
                text(
                    """
                    INSERT INTO inventory_events (
                        id, household_id, article_id, household_article_id, article_name,
                        location_id, location_label, event_type, quantity, old_quantity, new_quantity,
                        source, note, created_at
                    ) VALUES (
                        :id, :household_id, :article_id, :household_article_id, :article_name,
                        NULL, NULL, :event_type, :quantity, :old_quantity, :new_quantity,
                        'f5-12-regression', :note, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": event_id,
                    "household_id": HOUSEHOLD_ID,
                    "article_id": ARTICLE_ID,
                    "household_article_id": ARTICLE_ID,
                    "article_name": ARTICLE_NAME,
                    "event_type": event_type,
                    "quantity": quantity,
                    "old_quantity": old_quantity,
                    "new_quantity": new_quantity,
                    "note": note,
                },
            )

        article_rows = main_module.get_household_article_event_rows(
            conn,
            HOUSEHOLD_ID,
            ARTICLE_ID,
        )
        product_rows = main_module.get_household_product_event_rows(
            conn,
            HOUSEHOLD_ID,
            ARTICLE_ID,
            None,
        )

        persisted = conn.execute(
            text(
                """
                SELECT id, location_id, location_label, event_type
                FROM inventory_events
                WHERE household_id = :household_id
                  AND id IN (:purchase_id, :consume_id)
                ORDER BY id
                """
            ),
            {
                "household_id": HOUSEHOLD_ID,
                "purchase_id": PURCHASE_EVENT_ID,
                "consume_id": CONSUME_EVENT_ID,
            },
        ).mappings().all()
        assert len(persisted) == 2, persisted
        assert all(row.get("location_id") is None for row in persisted), persisted
        assert all(str(row.get("location_label") or "") == "" for row in persisted), persisted

        spaces_after_projection = int(
            conn.execute(
                text("SELECT COUNT(*) FROM spaces WHERE household_id = :household_id"),
                {"household_id": HOUSEHOLD_ID},
            ).scalar_one()
        )
        assert spaces_after_projection == 0, spaces_after_projection

    authorization = f"Bearer {main_module.build_auth_token(ADMIN_EMAIL)}"
    endpoint_rows = main_module.article_history(ARTICLE_NAME, authorization=authorization)["rows"]

    assert_locationless_history(article_rows, "article detail/history")
    assert_locationless_history(product_rows, "product event projection")
    assert_locationless_history(endpoint_rows, "legacy article history endpoint")

    with engine.begin() as conn:
        spaces_after_endpoint = int(
            conn.execute(
                text("SELECT COUNT(*) FROM spaces WHERE household_id = :household_id"),
                {"household_id": HOUSEHOLD_ID},
            ).scalar_one()
        )
        assert spaces_after_endpoint == 0, spaces_after_endpoint

    print("PASS household_location_tracking_level_none")
    print("PASS locationless_purchase_and_consume_persisted")
    print("PASS article_history_keeps_locationless_events")
    print("PASS product_history_keeps_locationless_events")
    print("PASS legacy_history_endpoint_keeps_locationless_events")
    print("PASS history_read_does_not_create_locations")
    print("F5_12_POSTGRESQL_LOCATIONLESS_HISTORY_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
