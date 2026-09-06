from __future__ import annotations

import os
from sqlalchemy import text
from app.db import engine


def required(name: str) -> str:
    value = str(os.environ.get(name, "")).strip()
    if not value:
        raise AssertionError(f"{name} ontbreekt voor L4-06")
    return value


def main() -> int:
    household_id = required("L4_HOUSEHOLD_ID")
    receipt_id = required("L4_RECEIPT_ID")
    batch_id = required("L4_BATCH_ID")
    line_a_id = required("L4_LINE_A_ID")
    line_b_id = required("L4_LINE_B_ID")
    article_a_id = required("L4_ARTICLE_A_ID")
    article_b_id = required("L4_ARTICLE_B_ID")
    event_a_id = required("L4_EVENT_A_ID")
    event_b_id = required("L4_EVENT_B_ID")
    shared_name = required("L4_SHARED_ARTICLE_NAME")

    assert engine.dialect.name == "postgresql", engine.dialect.name
    assert line_a_id != line_b_id
    assert article_a_id != article_b_id
    assert event_a_id != event_b_id

    with engine.begin() as conn:
        current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
        runtime_create = bool(
            conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()
        )
        assert current_user == "rezzerv_app", current_user
        assert runtime_create is False

        receipt = conn.execute(
            text("SELECT id, household_id, approved_at FROM public.receipt_tables WHERE id = :receipt_id"),
            {"receipt_id": receipt_id},
        ).mappings().one()
        assert str(receipt["household_id"]) == household_id, receipt
        assert receipt["approved_at"] is not None, receipt

        batch = conn.execute(
            text("SELECT id, household_id FROM public.purchase_import_batches WHERE id = :batch_id"),
            {"batch_id": batch_id},
        ).mappings().one()
        assert str(batch["household_id"]) == household_id, batch

        lines = conn.execute(
            text(
                """
                SELECT id, processing_status, matched_household_article_id, processed_event_id
                FROM public.purchase_import_lines
                WHERE id IN (:line_a_id, :line_b_id)
                """
            ),
            {"line_a_id": line_a_id, "line_b_id": line_b_id},
        ).mappings().all()
        assert len(lines) == 2, lines
        line_by_id = {str(row["id"]): row for row in lines}
        assert str(line_by_id[line_a_id]["processing_status"]) == "processed", line_by_id[line_a_id]
        assert str(line_by_id[line_b_id]["processing_status"]) == "processed", line_by_id[line_b_id]
        assert str(line_by_id[line_a_id]["matched_household_article_id"]) == article_a_id, line_by_id[line_a_id]
        assert str(line_by_id[line_b_id]["matched_household_article_id"]) == article_b_id, line_by_id[line_b_id]
        assert str(line_by_id[line_a_id]["processed_event_id"]) == event_a_id, line_by_id[line_a_id]
        assert str(line_by_id[line_b_id]["processed_event_id"]) == event_b_id, line_by_id[line_b_id]

        articles = conn.execute(
            text(
                """
                SELECT id, household_id, custom_name, naam
                FROM public.household_articles
                WHERE id IN (:article_a_id, :article_b_id)
                """
            ),
            {"article_a_id": article_a_id, "article_b_id": article_b_id},
        ).mappings().all()
        assert len(articles) == 2, articles
        article_by_id = {str(row["id"]): row for row in articles}
        for article_id in (article_a_id, article_b_id):
            article = article_by_id[article_id]
            assert str(article["household_id"]) == household_id, article
            assert str(article["custom_name"] or "").strip() == shared_name, article

        events = conn.execute(
            text(
                """
                SELECT id, household_id, household_article_id, event_type, source
                FROM public.inventory_events
                WHERE id IN (:event_a_id, :event_b_id)
                """
            ),
            {"event_a_id": event_a_id, "event_b_id": event_b_id},
        ).mappings().all()
        assert len(events) == 2, events
        event_by_id = {str(row["id"]): row for row in events}
        assert str(event_by_id[event_a_id]["household_article_id"]) == article_a_id, event_by_id[event_a_id]
        assert str(event_by_id[event_b_id]["household_article_id"]) == article_b_id, event_by_id[event_b_id]
        for event in events:
            assert str(event["household_id"]) == household_id, event
            assert str(event["event_type"]) == "purchase", event
            assert str(event["source"]) == "store_import", event

        inventory_article_ids = {
            str(value)
            for value in conn.execute(
                text(
                    """
                    SELECT DISTINCT household_article_id
                    FROM public.inventory
                    WHERE household_id = :household_id
                      AND household_article_id IN (:article_a_id, :article_b_id)
                      AND COALESCE(status, 'active') = 'active'
                    """
                ),
                {
                    "household_id": household_id,
                    "article_a_id": article_a_id,
                    "article_b_id": article_b_id,
                },
            ).scalars().all()
        }
        assert inventory_article_ids == {article_a_id, article_b_id}, inventory_article_ids

    print(f"article_a_id={article_a_id}")
    print(f"article_b_id={article_b_id}")
    print(f"shared_name={shared_name}")
    print("P0_L4_06_POSTGRESQL_DISTINCT_IDENTITIES_GREEN")
    print("P0_L4_06_POSTGRESQL_RENAME_PRESERVES_IDENTITY_GREEN")
    print("P0_L4_06_POSTGRESQL_HISTORY_OWNERSHIP_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
