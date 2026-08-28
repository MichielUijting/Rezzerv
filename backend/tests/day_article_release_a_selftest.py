from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.day_article_service import (
    DIRECT_CONSUMPTION,
    STOCK,
    ensure_direct_location,
    get_default_inventory_handling,
    record_direct_consumption,
    set_default_inventory_handling,
)
from app.testing.authorization_schema_fixture import install_authorization_schema


def main() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                naam TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE spaces (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                household_id TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE sublocations (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                space_id TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO household_articles (id, household_id, naam)
            VALUES ('article-1', 'household-1', 'Verse broodjes')
        """))
        install_authorization_schema(conn)
        ensure_authorization_foundation(conn)

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
        assert all(str(row["quantity"]) in {"2", "2.0", "2.00"} for row in events)
        assert all(row["space_id"] == direct["space_id"] for row in events)
        assert all(row["sublocation_id"] == direct["sublocation_id"] for row in events)

        inventory_count = conn.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='inventory'" )).scalar_one()
        assert inventory_count == 0

    print("DAY_ARTICLE_RELEASE_A_SELFTEST=PASS")


if __name__ == "__main__":
    main()
