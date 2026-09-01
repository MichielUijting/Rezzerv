"""Slice 2B4 PostgreSQL contract: inventory identity is household_article_id, never name."""

from fastapi import HTTPException
from sqlalchemy import text

from app.services.canonical_inventory_identity_service import (
    apply_inventory_purchase_by_identity,
    get_inventory_total_by_household_article,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
    seed_household,
)


def main() -> int:
    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    try:
        with engine.begin() as conn:
            seed_household(conn, household_id="A", name="Huishouden A")
            seed_household(conn, household_id="B", name="Huishouden B")
            conn.execute(text("""
                INSERT INTO household_articles (id, household_id, naam, status) VALUES
                  ('ha-a', 'A', 'Mosterd', 'active'),
                  ('ha-b', 'B', 'Mosterd', 'active'),
                  ('ha-a-2', 'A', 'Mosterd', 'active')
            """))
            # Zelfde naam, andere ID: mag nooit worden samengevoegd.
            conn.execute(text("""
                INSERT INTO inventory
                    (id, naam, aantal, household_id, household_article_id,
                     space_id, sublocation_id, status, updated_at)
                VALUES
                    ('inv-a-other', 'Mosterd', 7, 'A', 'ha-a-2', NULL, NULL, 'active', CURRENT_TIMESTAMP),
                    ('inv-b', 'Mosterd', 9, 'B', 'ha-b', NULL, NULL, 'active', CURRENT_TIMESTAMP)
            """))

            assert get_inventory_total_by_household_article(conn, "A", "ha-a") == 0
            inventory_id = apply_inventory_purchase_by_identity(
                conn,
                household_id="A",
                household_article_id="ha-a",
                quantity=2,
                space_id=None,
                sublocation_id=None,
            )
            assert inventory_id not in {"inv-a-other", "inv-b"}
            assert get_inventory_total_by_household_article(conn, "A", "ha-a") == 2
            assert get_inventory_total_by_household_article(conn, "A", "ha-a-2") == 7
            assert get_inventory_total_by_household_article(conn, "B", "ha-b") == 9

            same_inventory_id = apply_inventory_purchase_by_identity(
                conn,
                household_id="A",
                household_article_id="ha-a",
                quantity=3,
                space_id=None,
                sublocation_id=None,
            )
            assert same_inventory_id == inventory_id
            assert get_inventory_total_by_household_article(conn, "A", "ha-a") == 5

            row = conn.execute(
                text(
                    "SELECT naam, household_article_id, aantal "
                    "FROM inventory WHERE id = :id"
                ),
                {"id": inventory_id},
            ).mappings().one()
            assert row["naam"] == "Mosterd"
            assert row["household_article_id"] == "ha-a"
            assert int(row["aantal"]) == 5

            try:
                apply_inventory_purchase_by_identity(
                    conn,
                    household_id="A",
                    household_article_id="ha-b",
                    quantity=1,
                    space_id=None,
                    sublocation_id=None,
                )
            except HTTPException as exc:
                assert exc.status_code == 404
            else:
                raise AssertionError(
                    "cross-household household_article_id werd ten onrechte geaccepteerd"
                )
    finally:
        engine.dispose()

    print("PASS inventory identity uses household_article_id on PostgreSQL")
    print("PASS same-name household articles remain separate")
    print("PASS household isolation")
    print("PASS inventory.naam is snapshot only")
    print("HOUSEHOLD_ARTICLE_IDENTITY_SLICE2B4_INVENTORY_POSTGRESQL_GREEN")
    print("HOUSEHOLD_ARTICLE_IDENTITY_SLICE2B4_INVENTORY_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
