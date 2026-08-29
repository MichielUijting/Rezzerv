from sqlalchemy import create_engine, text

from app.api.superuser_household_routes import _actor_rows, _members
from app.services.actor_attribution_service import (
    bind_current_actor,
    clear_current_actor,
    install_actor_attribution_tracking,
)
from app.services.membership_user_identity_service import backfill_membership_user_ids


def test_legacy_membership_email_is_normalized_to_same_actor_id_as_server_session():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                user_id TEXT,
                user_email TEXT,
                role TEXT,
                status TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                created_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE actor_object_attributions (
                object_type TEXT NOT NULL,
                object_id TEXT NOT NULL,
                household_id TEXT NOT NULL,
                actor_user_id TEXT NOT NULL,
                attribution_source TEXT NOT NULL DEFAULT 'runtime_session',
                first_attributed_at TEXT NOT NULL,
                last_attributed_at TEXT NOT NULL,
                PRIMARY KEY (object_type, object_id)
            )
        """))
        conn.execute(text("""
            CREATE INDEX idx_actor_object_attributions_household_actor
            ON actor_object_attributions (household_id, actor_user_id, object_type)
        """))
        conn.execute(
            text("INSERT INTO app_users(id, email) VALUES (:id, :email)"),
            {"id": "canonical-admin-id", "email": "Admin@Rezzerv.local"},
        )
        conn.execute(
            text("""
                INSERT INTO household_memberships(
                    id, household_id, user_id, user_email, role, status
                ) VALUES (
                    'membership-admin', 'molenstraat', 'legacy-or-stale-id',
                    'admin@rezzerv.local', 'owner', 'active'
                )
            """),
        )

        assert backfill_membership_user_ids(conn) == 1
        membership = conn.execute(text("""
            SELECT user_id, user_email
            FROM household_memberships
            WHERE id = 'membership-admin'
        """)).mappings().one()
        assert membership["user_id"] == "canonical-admin-id"

        members = _members(conn, "molenstraat")
        assert len(members) == 1
        assert members[0]["user_id"] == "canonical-admin-id"
        assert str(members[0]["email"]).lower() == "admin@rezzerv.local"

    install_actor_attribution_tracking(engine)
    bind_current_actor("canonical-admin-id", "molenstraat")
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO receipt_tables(id, household_id, created_at)
                    VALUES ('receipt-new-admin', 'molenstraat', CURRENT_TIMESTAMP)
                """),
            )
    finally:
        clear_current_actor()

    with engine.begin() as conn:
        admin_rows = _actor_rows(
            conn,
            "receipt_tables",
            "receipt",
            "molenstraat",
            ("id", "created_at"),
            user_id="canonical-admin-id",
        )
        stale_rows = _actor_rows(
            conn,
            "receipt_tables",
            "receipt",
            "molenstraat",
            ("id", "created_at"),
            user_id="legacy-or-stale-id",
        )

    assert [(row["id"], row["actor_user_id"]) for row in admin_rows] == [
        ("receipt-new-admin", "canonical-admin-id")
    ]
    assert stale_rows == []


def test_membership_backfill_does_not_guess_without_unique_email_match():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE app_users (id TEXT PRIMARY KEY, email TEXT NOT NULL)"))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                user_id TEXT,
                user_email TEXT
            )
        """))
        conn.execute(text("INSERT INTO app_users(id, email) VALUES ('u1', 'same@rezzerv.local')"))
        conn.execute(text("INSERT INTO app_users(id, email) VALUES ('u2', 'SAME@rezzerv.local')"))
        conn.execute(text("""
            INSERT INTO household_memberships(id, household_id, user_id, user_email)
            VALUES ('m1', 'h1', NULL, 'same@rezzerv.local')
        """))

        assert backfill_membership_user_ids(conn) == 0
        user_id = conn.execute(text("SELECT user_id FROM household_memberships WHERE id='m1'" )).scalar()
        assert user_id is None
