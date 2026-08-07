"""Slice 2B4 contract: voorraadidentiteit is household_article_id, nooit naam."""

from sqlalchemy import create_engine, text
from fastapi import HTTPException

from app.services.canonical_inventory_identity_service import (
    apply_inventory_purchase_by_identity,
    get_inventory_total_by_household_article,
)


def main() -> int:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                naam TEXT NOT NULL,
                status TEXT DEFAULT 'active'
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory (
                id TEXT PRIMARY KEY,
                naam TEXT,
                aantal INTEGER,
                household_id TEXT NOT NULL,
                household_article_id TEXT,
                space_id TEXT,
                sublocation_id TEXT,
                status TEXT DEFAULT 'active',
                updated_at DATETIME
            )
        """))
        conn.execute(text("""
            INSERT INTO household_articles (id, household_id, naam, status) VALUES
              ('ha-a', 'A', 'Mosterd', 'active'),
              ('ha-b', 'B', 'Mosterd', 'active'),
              ('ha-a-2', 'A', 'Mosterd', 'active')
        """))
        # Zelfde naam, andere ID: mag nooit worden samengevoegd.
        conn.execute(text("""
            INSERT INTO inventory
                (id, naam, aantal, household_id, household_article_id, space_id, sublocation_id, status)
            VALUES
                ('inv-a-other', 'Mosterd', 7, 'A', 'ha-a-2', 'space-1', 'shelf-1', 'active'),
                ('inv-b', 'Mosterd', 9, 'B', 'ha-b', 'space-1', 'shelf-1', 'active')
        """))

        assert get_inventory_total_by_household_article(conn, 'A', 'ha-a') == 0
        inventory_id = apply_inventory_purchase_by_identity(
            conn,
            household_id='A',
            household_article_id='ha-a',
            quantity=2,
            space_id='space-1',
            sublocation_id='shelf-1',
        )
        assert inventory_id not in {'inv-a-other', 'inv-b'}
        assert get_inventory_total_by_household_article(conn, 'A', 'ha-a') == 2
        assert get_inventory_total_by_household_article(conn, 'A', 'ha-a-2') == 7
        assert get_inventory_total_by_household_article(conn, 'B', 'ha-b') == 9

        same_inventory_id = apply_inventory_purchase_by_identity(
            conn,
            household_id='A',
            household_article_id='ha-a',
            quantity=3,
            space_id='space-1',
            sublocation_id='shelf-1',
        )
        assert same_inventory_id == inventory_id
        assert get_inventory_total_by_household_article(conn, 'A', 'ha-a') == 5

        row = conn.execute(text("SELECT naam, household_article_id, aantal FROM inventory WHERE id = :id"), {'id': inventory_id}).mappings().one()
        assert row['naam'] == 'Mosterd'  # snapshot/presentatie
        assert row['household_article_id'] == 'ha-a'
        assert int(row['aantal']) == 5

        try:
            apply_inventory_purchase_by_identity(
                conn,
                household_id='A',
                household_article_id='ha-b',
                quantity=1,
                space_id='space-1',
                sublocation_id='shelf-1',
            )
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError('cross-household household_article_id werd ten onrechte geaccepteerd')

    print('PASS inventory identity uses household_article_id')
    print('PASS same-name household articles remain separate')
    print('PASS household isolation')
    print('PASS inventory.naam is snapshot only')
    print('HOUSEHOLD_ARTICLE_IDENTITY_SLICE2B4_INVENTORY_GREEN')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
