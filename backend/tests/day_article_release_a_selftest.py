from __future__ import annotations

import os
from decimal import Decimal

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.day_article_service import (
    DIRECT_CONSUMPTION,
    STOCK,
    ensure_direct_location,
    get_default_inventory_handling,
    record_direct_consumption,
    set_default_inventory_handling,
)


def _postgresql_engine():
    raw_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        raise RuntimeError("DATABASE_URL is required")
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError(
            "DAY_ARTICLE_RELEASE_A_SELFTEST requires PostgreSQL; "
            f"configured datastore={url.drivername!r}"
        )
    return create_engine(url, future=True)


def main() -> None:
    engine = _postgresql_engine()
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                assert conn.dialect.name == "postgresql", conn.dialect.name
                current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
                runtime_create = bool(
                    conn.execute(
                        text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                    ).scalar_one()
                )
                revision = str(
                    conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one()
                )
                assert current_user == "rezzerv_app", current_user
                assert runtime_create is False
                assert revision

                ensure_authorization_foundation(conn)
                conn.execute(text("""
                    INSERT INTO household_articles (
                        id,
                        household_id,
                        naam,
                        consumable,
                        updated_at
                    ) VALUES (
                        'article-1',
                        'household-1',
                        'Verse broodjes',
                        1,
                        CURRENT_TIMESTAMP
                    )
                """))

                initial = get_default_inventory_handling(conn, "household-1", "article-1")
                assert initial["default_inventory_handling"] == STOCK

                updated = set_default_inventory_handling(
                    conn,
                    household_id="household-1",
                    household_article_id="article-1",
                    handling=DIRECT_CONSUMPTION,
                    actor_user_id="admin-1",
                )
                assert updated["default_inventory_handling"] == DIRECT_CONSUMPTION

                direct = ensure_direct_location(conn, "household-1")
                assert direct["location"] == "Direct"
                assert direct["sublocation"] == "Direct"

                processed = record_direct_consumption(
                    conn,
                    household_id="household-1",
                    household_article_id="article-1",
                    quantity="2",
                    idempotency_key="receipt-line-1",
                    actor_user_id="member-1",
                )
                assert processed["quantity_received"] == "2"
                assert processed["quantity_consumed"] == "2"
                assert processed["net_inventory_change"] == "0"
                assert processed["idempotent_replay"] is False

                replay = record_direct_consumption(
                    conn,
                    household_id="household-1",
                    household_article_id="article-1",
                    quantity="2",
                    idempotency_key="receipt-line-1",
                    actor_user_id="member-1",
                )
                assert replay["idempotent_replay"] is True

                events = conn.execute(text("""
                    SELECT event_type, quantity, space_id, sublocation_id
                    FROM day_article_processing_events
                    WHERE household_id = 'household-1' AND idempotency_key = 'receipt-line-1'
                    ORDER BY event_type
                """)).mappings().all()
                assert len(events) == 2
                assert {row["event_type"] for row in events} == {"RECEIPT", "DIRECT_CONSUMPTION"}
                assert all(Decimal(str(row["quantity"])) == Decimal("2") for row in events)
                assert all(row["space_id"] == direct["space_id"] for row in events)
                assert all(row["sublocation_id"] == direct["sublocation_id"] for row in events)

                assert inspect(conn).has_table("inventory")
                inventory_rows = conn.execute(text(
                    "SELECT COUNT(*) FROM inventory WHERE household_id = 'household-1'"
                )).scalar_one()
                assert inventory_rows == 0

                print(f"runtime_user={current_user}")
                print(f"alembic_head={revision}")
                print("DAY_ARTICLE_RELEASE_A_POSTGRESQL_RUNTIME_GREEN")
            finally:
                transaction.rollback()
    finally:
        engine.dispose()

    print("DAY_ARTICLE_RELEASE_A_SELFTEST=PASS")


if __name__ == "__main__":
    main()
