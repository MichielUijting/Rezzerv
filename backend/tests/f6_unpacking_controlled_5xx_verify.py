"""PostgreSQL end-state proof for the F6-01 Unpacking controlled-500 authority."""
from __future__ import annotations

import os
from decimal import Decimal

from sqlalchemy import text

from app.db import engine


def required(name: str) -> str:
    value = str(os.getenv(name, "") or "").strip()
    assert value, f"{name} ontbreekt"
    return value


def main() -> None:
    household_id = required("F6_UNPACKING_HOUSEHOLD_ID")
    article_id = required("F6_UNPACKING_ARTICLE_ID")
    batch_id = required("F6_UNPACKING_BATCH_ID")
    line_id = required("F6_UNPACKING_LINE_ID")
    expected_quantity = Decimal(required("F6_UNPACKING_EXPECTED_QUANTITY"))

    assert engine.dialect.name == "postgresql", engine.dialect.name

    with engine.begin() as conn:
        current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
        runtime_create = bool(
            conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()
        )
        assert current_user == "rezzerv_app", current_user
        assert runtime_create is False

        batch = conn.execute(
            text(
                """
                SELECT id, household_id, import_status, processed_at
                FROM purchase_import_batches
                WHERE id = :batch_id
                """
            ),
            {"batch_id": batch_id},
        ).mappings().one()
        assert str(batch["household_id"]) == household_id, batch
        assert str(batch["import_status"]) == "reviewed", batch
        assert batch["processed_at"] is None, batch

        line = conn.execute(
            text(
                """
                SELECT id, batch_id, processing_status, processed_at,
                       processed_event_id, processing_error,
                       matched_household_article_id, target_location_id
                FROM purchase_import_lines
                WHERE id = :line_id AND batch_id = :batch_id
                """
            ),
            {"line_id": line_id, "batch_id": batch_id},
        ).mappings().one()
        assert str(line["processing_status"]) == "pending", line
        assert line["processed_at"] is None, line
        assert line["processed_event_id"] is None, line
        assert line["processing_error"] in (None, ""), line
        assert str(line["matched_household_article_id"]) == article_id, line
        assert str(line["target_location_id"] or "").strip(), line

        inventory_quantity = Decimal(
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
                    {"household_id": household_id, "article_id": article_id},
                ).scalar_one()
            )
        )
        assert inventory_quantity == expected_quantity, inventory_quantity

        day_article_event_count = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM day_article_processing_events
                    WHERE household_id = :household_id
                      AND household_article_id = :article_id
                      AND idempotency_key = :idempotency_key
                    """
                ),
                {
                    "household_id": household_id,
                    "article_id": article_id,
                    "idempotency_key": f"purchase-import-line:{line_id}",
                },
            ).scalar_one()
        )
        assert day_article_event_count == 0, day_article_event_count

        inventory_event_count = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM inventory_events
                    WHERE household_id = :household_id
                      AND household_article_id = :article_id
                    """
                ),
                {"household_id": household_id, "article_id": article_id},
            ).scalar_one()
        )
        assert inventory_event_count == 0, inventory_event_count

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
                {"household_id": household_id, "article_id": article_id},
            ).scalar_one()
        )
        assert direct_inventory_rows == 0, direct_inventory_rows

    print(f"runtime_user={current_user}")
    print(f"inventory_quantity={inventory_quantity}")
    print(f"day_article_event_count={day_article_event_count}")
    print(f"inventory_event_count={inventory_event_count}")
    print(f"direct_inventory_rows={direct_inventory_rows}")
    print("F6_UNPACKING_POSTGRESQL_ROLLBACK_GREEN")
    print("F6_UNPACKING_DB_CONSISTENCY_AFTER_ERROR_GREEN")


if __name__ == "__main__":
    main()
