from sqlalchemy import create_engine, text

from app.api.superuser_household_routes import _actor_rows
from app.services.actor_attribution_service import (
    bind_current_actor,
    clear_current_actor,
    install_actor_attribution_tracking,
)

HOUSEHOLD_ID = "0"
ADMIN_USER_ID = "admin@rezzerv.local"
MEMBER_USER_ID = "lid@rezzerv.local"


def _create_household_zero_domain_tables(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                retailer TEXT,
                purchase_at TEXT,
                created_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_batches (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                source_reference TEXT,
                import_status TEXT,
                created_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                article_name TEXT,
                event_type TEXT,
                quantity NUMERIC,
                created_at TEXT
            )
        """))


def _write_user_actions(engine, user_id: str, suffix: str):
    bind_current_actor(user_id, HOUSEHOLD_ID)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO receipt_tables(id, household_id, retailer, purchase_at, created_at)
                    VALUES (:id, :household_id, :retailer, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """),
                {
                    "id": f"hh0-receipt-{suffix}",
                    "household_id": HOUSEHOLD_ID,
                    "retailer": f"Testwinkel {suffix}",
                },
            )
            conn.execute(
                text("""
                    INSERT INTO purchase_import_batches(
                        id, household_id, source_reference, import_status, created_at
                    ) VALUES (
                        :id, :household_id, :source_reference, 'processed', CURRENT_TIMESTAMP
                    )
                """),
                {
                    "id": f"hh0-batch-{suffix}",
                    "household_id": HOUSEHOLD_ID,
                    "source_reference": f"hh0-receipt-{suffix}",
                },
            )
            conn.execute(
                text("""
                    INSERT INTO inventory_events(
                        id, household_id, article_name, event_type, quantity, created_at
                    ) VALUES (
                        :id, :household_id, :article_name, 'purchase', 1, CURRENT_TIMESTAMP
                    )
                """),
                {
                    "id": f"hh0-event-{suffix}",
                    "household_id": HOUSEHOLD_ID,
                    "article_name": f"Testartikel {suffix}",
                },
            )
    finally:
        clear_current_actor()


def _write_unattributed_history(engine):
    """Simuleer historische Huishouden-0-data van vóór actorregistratie."""
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO receipt_tables(id, household_id, retailer, purchase_at, created_at)
                VALUES ('hh0-receipt-history', :household_id, 'Historische winkel', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {"household_id": HOUSEHOLD_ID},
        )
        conn.execute(
            text("""
                INSERT INTO purchase_import_batches(
                    id, household_id, source_reference, import_status, created_at
                ) VALUES (
                    'hh0-batch-history', :household_id, 'hh0-receipt-history', 'processed', CURRENT_TIMESTAMP
                )
            """),
            {"household_id": HOUSEHOLD_ID},
        )
        conn.execute(
            text("""
                INSERT INTO inventory_events(
                    id, household_id, article_name, event_type, quantity, created_at
                ) VALUES (
                    'hh0-event-history', :household_id, 'Historisch artikel', 'purchase', 1, CURRENT_TIMESTAMP
                )
            """),
            {"household_id": HOUSEHOLD_ID},
        )


def _project(conn, table: str, object_type: str, preferred, user_id=None):
    return _actor_rows(
        conn,
        table,
        object_type,
        HOUSEHOLD_ID,
        preferred,
        user_id=user_id,
    )


def test_household_zero_superuser_filter_exact_po_scenario():
    """Regressietest voor de PO-selectie in Superuser > Huishoudens > Huishouden 0.

    Scenario:
    - admin en lid voeren ieder een eigen kassabon-, uitpak- en voorraadhandeling uit;
    - alle gebruikers geselecteerd toont de volledige Huishouden-0-projectie;
    - alleen admin toont uitsluitend admins geattribueerde handelingen;
    - alleen lid toont uitsluitend lids geattribueerde handelingen;
    - admin + lid samen is exact de som van beide geattribueerde subsets;
    - geen selectie levert vanuit de UI-contractregel geen detailregels op;
    - historische niet-herleidbare regels blijven alleen in de volledige projectie zichtbaar.
    """
    engine = create_engine("sqlite:///:memory:")
    _create_household_zero_domain_tables(engine)
    install_actor_attribution_tracking(engine)

    _write_user_actions(engine, ADMIN_USER_ID, "admin")
    _write_user_actions(engine, MEMBER_USER_ID, "lid")
    _write_unattributed_history(engine)

    domains = (
        (
            "receipt_tables",
            "receipt",
            ("id", "retailer", "purchase_at", "created_at"),
            {"hh0-receipt-admin", "hh0-receipt-lid", "hh0-receipt-history"},
            "hh0-receipt-admin",
            "hh0-receipt-lid",
        ),
        (
            "purchase_import_batches",
            "unpack_batch",
            ("id", "source_reference", "import_status", "created_at"),
            {"hh0-batch-admin", "hh0-batch-lid", "hh0-batch-history"},
            "hh0-batch-admin",
            "hh0-batch-lid",
        ),
        (
            "inventory_events",
            "inventory_event",
            ("id", "article_name", "event_type", "quantity", "created_at"),
            {"hh0-event-admin", "hh0-event-lid", "hh0-event-history"},
            "hh0-event-admin",
            "hh0-event-lid",
        ),
    )

    with engine.begin() as conn:
        for table, object_type, preferred, expected_all, expected_admin, expected_lid in domains:
            all_rows = _project(conn, table, object_type, preferred)
            admin_rows = _project(conn, table, object_type, preferred, ADMIN_USER_ID)
            lid_rows = _project(conn, table, object_type, preferred, MEMBER_USER_ID)

            all_ids = {row["id"] for row in all_rows}
            admin_ids = {row["id"] for row in admin_rows}
            lid_ids = {row["id"] for row in lid_rows}

            assert all_ids == expected_all
            assert admin_ids == {expected_admin}
            assert lid_ids == {expected_lid}
            assert {row["actor_user_id"] for row in admin_rows} == {ADMIN_USER_ID}
            assert {row["actor_user_id"] for row in lid_rows} == {MEMBER_USER_ID}

            # A+B: de gecombineerde geselecteerde gebruikers leveren exact beide
            # geattribueerde regels op, maar niet de historische onbekende regel.
            combined_ids = admin_ids | lid_ids
            assert combined_ids == {expected_admin, expected_lid}
            assert combined_ids < all_ids

            # Geen gebruikers geselecteerd: dit is het productie-UI-contract.
            selected_user_ids = set()
            visible_rows = [
                row for row in all_rows
                if str(row.get("actor_user_id") or "") in selected_user_ids
            ]
            assert visible_rows == []

    with engine.begin() as conn:
        attribution_rows = conn.execute(text("""
            SELECT object_type, object_id, actor_user_id
            FROM actor_object_attributions
            WHERE household_id = :household_id
            ORDER BY object_type, object_id
        """), {"household_id": HOUSEHOLD_ID}).mappings().all()

    assert len(attribution_rows) == 6
    assert {row["actor_user_id"] for row in attribution_rows} == {
        ADMIN_USER_ID,
        MEMBER_USER_ID,
    }
    assert all(str(row.get("object_id") or "").startswith("hh0-") for row in attribution_rows)
