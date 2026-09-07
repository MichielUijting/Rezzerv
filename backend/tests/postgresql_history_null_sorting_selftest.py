from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app.db import engine
from app.testing.postgresql_onboarding_selftest_fixture import seed_admin_member_household


HOUSEHOLD_ID = "f5-11-history-null-sorting-household"
ADMIN_ID = "f5-11-history-null-sorting-admin"
ADMIN_EMAIL = "f5-11-history-null-sorting-admin@rezzerv.local"
PASSWORD = "F5HistoryNullSorting123!"
ARTICLE_ID = "f5-11-history-null-sorting-article"
ARTICLE_NAME = "F5-11 historie sorteerartikel"
EVENT_NEWEST_ID = "f5-11-event-newest"
EVENT_OLDER_ID = "f5-11-event-older"
EVENT_NULL_ID = "f5-11-event-null"
EXPECTED_ORDER = [EVENT_NEWEST_ID, EVENT_OLDER_ID, EVENT_NULL_ID]


def assert_history_order(rows: list[dict], label: str) -> None:
    ids = [str(row.get("id") or "") for row in rows]
    assert ids == EXPECTED_ORDER, (
        f"{label}: PostgreSQL Historie moet geldige created_at-waarden DESC tonen en NULL created_at als laatste; "
        f"expected={EXPECTED_ORDER} actual={ids}"
    )
    assert rows[0].get("created_at") is not None, rows
    assert rows[1].get("created_at") is not None, rows
    assert rows[2].get("created_at") is None, rows


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
        household_name="F5-11 Historie NULL sortering",
        admin_id=ADMIN_ID,
        admin_email=ADMIN_EMAIL,
        admin_password=PASSWORD,
        admin_membership_id="f5-11-history-null-sorting-admin-membership",
        member_id="f5-11-history-null-sorting-member",
        member_email="f5-11-history-null-sorting-member@rezzerv.local",
        member_password=PASSWORD,
        member_membership_id="f5-11-history-null-sorting-member-membership",
    )

    from app import main as main_module

    main_module.engine = engine

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO household_articles (
                    id, household_id, naam, consumable, created_at, updated_at, source, status
                ) VALUES (
                    :id, :household_id, :naam, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                    'f5-11-regression', 'active'
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"id": ARTICLE_ID, "household_id": HOUSEHOLD_ID, "naam": ARTICLE_NAME},
        )

        events = (
            (EVENT_OLDER_ID, datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc), "ouder gedateerd event"),
            (EVENT_NEWEST_ID, datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc), "nieuwste gedateerd event"),
            (EVENT_NULL_ID, None, "legacy event zonder created_at"),
        )
        for event_id, created_at, note in events:
            conn.execute(
                text(
                    """
                    INSERT INTO inventory_events (
                        id, household_id, article_id, household_article_id, article_name,
                        event_type, quantity, source, note, created_at
                    ) VALUES (
                        :id, :household_id, :article_id, :household_article_id, :article_name,
                        'purchase', 1, 'f5-11-regression', :note, :created_at
                    )
                    """
                ),
                {
                    "id": event_id,
                    "household_id": HOUSEHOLD_ID,
                    "article_id": ARTICLE_ID,
                    "household_article_id": ARTICLE_ID,
                    "article_name": ARTICLE_NAME,
                    "note": note,
                    "created_at": created_at,
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

    assert_history_order(article_rows, "article detail/history")
    assert_history_order(product_rows, "product event projection")

    print("PASS article_history_non_null_created_at_descending")
    print("PASS article_history_null_created_at_last")
    print("PASS product_history_non_null_created_at_descending")
    print("PASS product_history_null_created_at_last")
    print("F5_11_POSTGRESQL_HISTORY_NULL_SORTING_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
