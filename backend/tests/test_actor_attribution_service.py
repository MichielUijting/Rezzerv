from sqlalchemy import create_engine, text

from app.services.actor_attribution_service import (
    bind_current_actor,
    clear_current_actor,
    install_actor_attribution_tracking,
)


def test_two_users_are_attributed_to_their_own_receipts_unpack_batches_and_inventory_events():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                created_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_batches (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                created_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                article_name TEXT,
                created_at TEXT
            )
        """))

    install_actor_attribution_tracking(engine)

    bind_current_actor("user-a", "household-1")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO receipt_tables(id, household_id, created_at) VALUES (:id, :household_id, CURRENT_TIMESTAMP)"), {"id": "receipt-a", "household_id": "household-1"})
        conn.execute(text("INSERT INTO purchase_import_batches(id, household_id, created_at) VALUES (:id, :household_id, CURRENT_TIMESTAMP)"), {"id": "batch-a", "household_id": "household-1"})
        conn.execute(text("INSERT INTO inventory_events(id, household_id, article_name, created_at) VALUES (:id, :household_id, :article_name, CURRENT_TIMESTAMP)"), {"id": "event-a", "household_id": "household-1", "article_name": "A"})

    bind_current_actor("user-b", "household-1")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO receipt_tables(id, household_id, created_at) VALUES (:id, :household_id, CURRENT_TIMESTAMP)"), {"id": "receipt-b", "household_id": "household-1"})
        conn.execute(text("INSERT INTO purchase_import_batches(id, household_id, created_at) VALUES (:id, :household_id, CURRENT_TIMESTAMP)"), {"id": "batch-b", "household_id": "household-1"})
        conn.execute(text("INSERT INTO inventory_events(id, household_id, article_name, created_at) VALUES (:id, :household_id, :article_name, CURRENT_TIMESTAMP)"), {"id": "event-b", "household_id": "household-1", "article_name": "B"})

    clear_current_actor()
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT object_type, object_id, actor_user_id
            FROM actor_object_attributions
            WHERE household_id = 'household-1'
            ORDER BY object_type, object_id
        """)).mappings().all()

    assert {(row["object_type"], row["object_id"], row["actor_user_id"]) for row in rows} == {
        ("receipt", "receipt-a", "user-a"),
        ("receipt", "receipt-b", "user-b"),
        ("unpack_batch", "batch-a", "user-a"),
        ("unpack_batch", "batch-b", "user-b"),
        ("inventory_event", "event-a", "user-a"),
        ("inventory_event", "event-b", "user-b"),
    }
