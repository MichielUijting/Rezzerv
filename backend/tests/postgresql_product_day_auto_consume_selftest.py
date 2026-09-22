from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.product_day_auto_consume_service import (
    AUTO_CONSUME_ALL_EXISTING,
    AUTO_CONSUME_PURCHASED_QUANTITY,
    compute_product_day_auto_deduction,
)


DATABASE_URL = os.environ["DATABASE_URL"]


def _seed_event(
    conn,
    *,
    event_id: str,
    household_id: str = "pg-h1",
    article_id: str = "pg-a1",
    event_type: str,
    quantity: int,
    old_quantity: int,
    source: str,
    effective_at: str,
):
    conn.execute(
        text(
            """
            INSERT INTO inventory_events (
                id, household_id, household_article_id, event_type, quantity,
                old_quantity, source, purchase_date, effective_at,
                event_priority, source_reference, source_line_id
            ) VALUES (
                :id, :household_id, :article_id, :event_type, :quantity,
                :old_quantity, :source, '2026-08-26', CAST(:effective_at AS TIMESTAMPTZ),
                10, :source_reference, :source_line_id
            )
            """
        ),
        {
            "id": event_id,
            "household_id": household_id,
            "article_id": article_id,
            "event_type": event_type,
            "quantity": quantity,
            "old_quantity": old_quantity,
            "source": source,
            "effective_at": effective_at,
            "source_reference": f"receipt:{event_id}",
            "source_line_id": f"line:{event_id}",
        },
    )


def main() -> None:
    engine = create_engine(DATABASE_URL, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TEMP TABLE inventory_events (
                    id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL,
                    household_article_id TEXT,
                    event_type TEXT NOT NULL,
                    quantity NUMERIC NOT NULL,
                    old_quantity NUMERIC,
                    source TEXT NOT NULL,
                    purchase_date TEXT,
                    effective_at TIMESTAMPTZ,
                    event_priority INTEGER,
                    source_reference TEXT,
                    source_line_id TEXT
                ) ON COMMIT DROP
                """
            )
        )

        _seed_event(
            conn,
            event_id="p1",
            event_type="purchase",
            quantity=2,
            old_quantity=10,
            source="store_import",
            effective_at="2026-08-26T09:00:00+02:00",
        )
        _seed_event(
            conn,
            event_id="c1",
            event_type="auto_repurchase",
            quantity=-2,
            old_quantity=12,
            source="auto_repurchase",
            effective_at="2026-08-26T09:00:00+02:00",
        )
        cumulative = compute_product_day_auto_deduction(
            conn,
            household_id="pg-h1",
            household_article_id="pg-a1",
            purchase_date="2026-08-26T14:00:00+02:00",
            mode=AUTO_CONSUME_PURCHASED_QUANTITY,
            pre_purchase_total=10,
            purchased_quantity=3,
        )
        assert cumulative["day_start_stock"] == 10
        assert cumulative["prior_day_purchased_quantity"] == 2
        assert cumulative["prior_day_auto_consumed_quantity"] == 2
        assert cumulative["requested_deduction_quantity"] == 3
        print("POSTGRESQL_PRODUCT_DAY_AUTO_CONSUME_CUMULATIVE_GREEN")

        conn.execute(text("DELETE FROM inventory_events"))
        _seed_event(
            conn,
            event_id="p-late",
            event_type="purchase",
            quantity=2,
            old_quantity=5,
            source="store_import",
            effective_at="2026-08-26T14:00:00+02:00",
        )
        _seed_event(
            conn,
            event_id="c-late",
            event_type="auto_repurchase",
            quantity=-5,
            old_quantity=7,
            source="auto_repurchase",
            effective_at="2026-08-26T14:00:00+02:00",
        )
        backdated = compute_product_day_auto_deduction(
            conn,
            household_id="pg-h1",
            household_article_id="pg-a1",
            purchase_date="2026-08-26T09:00:00+02:00",
            mode=AUTO_CONSUME_ALL_EXISTING,
            pre_purchase_total=2,
            purchased_quantity=3,
        )
        assert backdated["day_start_stock"] == 5
        assert backdated["cumulative_day_purchased_quantity"] == 5
        assert backdated["requested_deduction_quantity"] == 0
        print("POSTGRESQL_PRODUCT_DAY_AUTO_CONSUME_BACKDATED_GREEN")

        _seed_event(
            conn,
            event_id="other-household",
            household_id="pg-h2",
            event_type="purchase",
            quantity=9,
            old_quantity=30,
            source="store_import",
            effective_at="2026-08-26T07:00:00+02:00",
        )
        isolated = compute_product_day_auto_deduction(
            conn,
            household_id="pg-h1",
            household_article_id="pg-a1",
            purchase_date="2026-08-26",
            mode=AUTO_CONSUME_PURCHASED_QUANTITY,
            pre_purchase_total=2,
            purchased_quantity=1,
        )
        assert isolated["prior_day_purchased_quantity"] == 2
        print("POSTGRESQL_PRODUCT_DAY_AUTO_CONSUME_HOUSEHOLD_ISOLATION_GREEN")

    engine.dispose()
    print("POSTGRESQL_PRODUCT_DAY_AUTO_CONSUME_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
