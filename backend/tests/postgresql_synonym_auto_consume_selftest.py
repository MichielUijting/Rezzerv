"""Real PostgreSQL 17 synonym repurchase transaction with disposable temp tables.

No production schema/data and no migration; runs in a dedicated CI database.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.synonym_auto_consume_service import (
    plan_confirmed_synonym_deduction,
    apply_confirmed_synonym_deduction,
)


def seed(conn, *, household="pg-h1", quantity_a=2, quantity_b=3, quantity_c=0):
    conn.execute(text("DELETE FROM inventory_events"))
    conn.execute(text("DELETE FROM inventory"))
    conn.execute(text("DELETE FROM article_synonym_links"))
    conn.execute(text("DELETE FROM household_articles"))
    conn.execute(text("DELETE FROM global_products"))
    conn.execute(text("""
        INSERT INTO global_products (id,status,size_value,size_unit) VALUES ('gp-a','active',1,'stuk'),('gp-b','active',1,'stuk'),('gp-c','active',1,'stuk')
    """))
    conn.execute(text("""
        INSERT INTO article_synonym_links VALUES ('gp-a','gp-b'),('gp-b','gp-c')
    """))
    conn.execute(text("""
        INSERT INTO household_articles
         (id,household_id,naam,global_product_id,status,default_inventory_handling)
        VALUES ('ha-a',:household,'Melk AH','gp-a','active','STOCK'),
               ('ha-b',:household,'Melk Jumbo','gp-b','active','STOCK'),
               ('ha-c',:household,'Melk Lidl','gp-c','active','STOCK'),
               ('foreign-b','pg-other','Melk Jumbo','gp-b','active','STOCK')
    """), {"household": household})
    for inv_id, article_id, number, location in (
        ("inv-a", "ha-a", quantity_a, "fridge"),
        ("inv-b", "ha-b", quantity_b, "pantry"),
        ("inv-c", "ha-c", quantity_c, "cellar"),
        ("foreign", "foreign-b", 99, "foreign-loc"),
    ):
        if number:
            conn.execute(text("""
                INSERT INTO inventory (id,household_id,household_article_id,aantal,
                  space_id,sublocation_id,status)
                VALUES (:id,:household,:article,:qty,:location,NULL,'active')
            """), {"id": inv_id, "household": ("pg-other" if inv_id == "foreign" else household),
                   "article": article_id, "qty": number, "location": location})


def stock(conn, article_id, household="pg-h1"):
    return int(conn.execute(text("""
        SELECT COALESCE(SUM(aantal),0) FROM inventory
        WHERE household_id=:household AND household_article_id=:article
    """), {"household": household, "article": article_id}).scalar())


def record_purchase(conn, *, article_id, quantity, location, inventory_id, day="2026-11-10"):
    next_id = "buy-" + article_id + "-" + str(conn.execute(text(
        "SELECT COUNT(*) FROM inventory_events WHERE event_type='purchase'"
    )).scalar())
    conn.execute(text("""
        INSERT INTO inventory_events
         (id,household_id,household_article_id,event_type,source,quantity,location_id,purchase_date)
        VALUES (:id,'pg-h1',:article,'purchase','store_import',:quantity,:location,:day)
    """), {"id": next_id, "article": article_id, "quantity": quantity,
           "location": location, "day": day})
    exists = conn.execute(text(
        "SELECT 1 FROM inventory WHERE id=:id"
    ), {"id": inventory_id}).scalar()
    if exists:
        conn.execute(text("UPDATE inventory SET aantal=aantal+:q WHERE id=:id"),
                     {"id": inventory_id, "q": quantity})
    else:
        conn.execute(text("""
            INSERT INTO inventory
            (id,household_id,household_article_id,aantal,space_id,sublocation_id,status)
            VALUES (:id,'pg-h1',:article,:q,:location,NULL,'active')
        """), {"id": inventory_id, "article": article_id, "q": quantity,
               "location": location})


def apply(conn, plan, *, purchased_article, quantity, inventory_id):
    counter = [0]

    def event(connection, household_id, article_id, name, resolved_location, *,
              quantity, purchase_date):
        counter[0] += 1
        event_id = "auto-" + str(counter[0]) + "-" + str(
            connection.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar()
        )
        connection.execute(text("""
            INSERT INTO inventory_events
             (id,household_id,household_article_id,event_type,source,
              quantity,location_id,purchase_date)
            VALUES (:id,:household,:article,'auto_repurchase','auto_repurchase',
                    :q,:location,:day)
        """), {"id": event_id, "household": household_id, "article": article_id,
               "q": -quantity, "location": resolved_location["location_id"],
               "day": purchase_date})
        return event_id

    return apply_confirmed_synonym_deduction(
        conn, household_id="pg-h1", purchased_article_id=purchased_article,
        purchased_quantity=quantity, purchase_inventory_id=inventory_id,
        resolved_location={"location_id": "fridge"},
        plan=plan, create_auto_event=event,
    )


def plan(conn, *, article, quantity, mode):
    return plan_confirmed_synonym_deduction(
        conn, household_id="pg-h1", purchased_article_id=article,
        purchase_date="2026-11-10", purchased_quantity=quantity,
        household_mode=mode, effective_mode_for_article=lambda article_id, name: mode,
    )


def main():
    if not os.environ["DATABASE_URL"].startswith("postgresql+"):
        raise RuntimeError("PostgreSQL is required")
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TEMP TABLE global_products (id TEXT PRIMARY KEY,status TEXT,size_value NUMERIC,size_unit TEXT) ON COMMIT DROP
        """))
        conn.execute(text("""
            CREATE TEMP TABLE household_articles (
                id TEXT PRIMARY KEY,household_id TEXT,naam TEXT,global_product_id TEXT,
                status TEXT,default_inventory_handling TEXT
            ) ON COMMIT DROP
        """))
        conn.execute(text("""
            CREATE TEMP TABLE article_synonym_links (
                left_product_id TEXT,right_product_id TEXT
            ) ON COMMIT DROP
        """))
        conn.execute(text("""
            CREATE TEMP TABLE inventory (
                id TEXT PRIMARY KEY,household_id TEXT,household_article_id TEXT,
                aantal NUMERIC,space_id TEXT,sublocation_id TEXT,status TEXT,
                updated_at TIMESTAMPTZ
            ) ON COMMIT DROP
        """))
        conn.execute(text("""
            CREATE TEMP TABLE inventory_events (
                id TEXT PRIMARY KEY,household_id TEXT,household_article_id TEXT,
                event_type TEXT,source TEXT,quantity NUMERIC,location_id TEXT,
                purchase_date TEXT
            ) ON COMMIT DROP
        """))

        # All-existing mode: A purchase consumes old B stock at B's pantry
        # and old A stock at A's fridge, never stock newly bought at A.
        seed(conn)
        group = plan(conn, article="ha-a", quantity=2,
                     mode="consume_all_existing_before_purchase")
        assert group is not None and group["requested_deduction_quantity"] == 5, group
        record_purchase(conn, article_id="ha-a", quantity=2,
                        location="fridge", inventory_id="inv-a")
        result = apply(conn, group, purchased_article="ha-a",
                       quantity=2, inventory_id="inv-a")
        assert result["applied_quantity"] == 5
        assert stock(conn, "ha-a") == 2 and stock(conn, "ha-b") == 0
        assert stock(conn, "foreign-b", "pg-other") == 99
        locations = dict(conn.execute(text("""
            SELECT location_id, ABS(quantity) FROM inventory_events
            WHERE event_type='auto_repurchase'
        """)).all())
        assert locations == {"fridge": 2, "pantry": 3}, locations
        # Another shop on the same day must not consume the new stock again.
        second = plan(conn, article="ha-b", quantity=2,
                      mode="consume_all_existing_before_purchase")
        assert second is not None and second["requested_deduction_quantity"] == 0
        record_purchase(conn, article_id="ha-b", quantity=2,
                        location="pantry", inventory_id="inv-b")
        assert stock(conn, "ha-a") == 2 and stock(conn, "ha-b") == 2
        print("SYNONYM_POSTGRESQL_ALL_EXISTING_LOCATION_ISOLATION_GREEN")

        # Quantity mode: second shop consumes only the remaining OLD stock.
        seed(conn)
        first = plan(conn, article="ha-a", quantity=2, mode="consume_purchased_quantity")
        assert first["requested_deduction_quantity"] == 2
        record_purchase(conn, article_id="ha-a", quantity=2,
                        location="fridge", inventory_id="inv-a")
        apply(conn, first, purchased_article="ha-a", quantity=2, inventory_id="inv-a")
        assert stock(conn, "ha-a") == 4 and stock(conn, "ha-b") == 1
        second = plan(conn, article="ha-b", quantity=3, mode="consume_purchased_quantity")
        assert second["requested_deduction_quantity"] == 3, second
        record_purchase(conn, article_id="ha-b", quantity=3,
                        location="pantry", inventory_id="inv-b")
        apply(conn, second, purchased_article="ha-b", quantity=3, inventory_id="inv-b")
        assert stock(conn, "ha-a") == 2 and stock(conn, "ha-b") == 3
        assert stock(conn, "foreign-b", "pg-other") == 99
        print("SYNONYM_POSTGRESQL_CUMULATIVE_PRODUCT_DAY_GREEN")

        # Three linked products A-B-C form one confirmed group, even though
        # there is no direct A-C link. All three old stock locations are
        # consumed and a new Lidl purchase is kept untouched.
        seed(conn, quantity_a=2, quantity_b=3, quantity_c=4)
        grouped = plan(conn, article="ha-c", quantity=2,
                       mode="consume_all_existing_before_purchase")
        assert grouped is not None and grouped["members"] == ("ha-a", "ha-b", "ha-c"), grouped
        assert grouped["requested_deduction_quantity"] == 9
        record_purchase(conn, article_id="ha-c", quantity=2,
                        location="cellar", inventory_id="inv-c")
        applied = apply(conn, grouped, purchased_article="ha-c",
                        quantity=2, inventory_id="inv-c")
        assert applied["applied_quantity"] == 9
        assert stock(conn, "ha-a") == 0 and stock(conn, "ha-b") == 0
        assert stock(conn, "ha-c") == 2
        assert stock(conn, "foreign-b", "pg-other") == 99
        three_locations = dict(conn.execute(text("""
            SELECT location_id, ABS(quantity) FROM inventory_events
            WHERE event_type='auto_repurchase'
        """)).all())
        assert three_locations == {"fridge": 2, "pantry": 3, "cellar": 4}
        second = plan(conn, article="ha-a", quantity=3,
                      mode="consume_all_existing_before_purchase")
        assert second is not None and second["requested_deduction_quantity"] == 0
        print("SYNONYM_POSTGRESQL_THREE_MEMBER_CHAIN_GREEN")

        # Quantity mode rolls across all three individual product identities.
        seed(conn, quantity_a=2, quantity_b=3, quantity_c=4)
        group = plan(conn, article="ha-a", quantity=6, mode="consume_purchased_quantity")
        assert group is not None and group["requested_deduction_quantity"] == 6
        record_purchase(conn, article_id="ha-a", quantity=6,
                        location="fridge", inventory_id="inv-a")
        applied = apply(conn, group, purchased_article="ha-a",
                        quantity=6, inventory_id="inv-a")
        assert applied["applied_quantity"] == 6
        assert stock(conn, "ha-a") == 8 and stock(conn, "ha-b") == 0
        assert stock(conn, "ha-c") == 1
        print("SYNONYM_POSTGRESQL_THREE_MEMBER_QUANTITY_GREEN")

        # Disabled mode is a strict non-deduction even with confirmed pairs.
        seed(conn)
        assert plan(conn, article="ha-a", quantity=2, mode="none") is None
        assert stock(conn, "ha-a") == 2 and stock(conn, "ha-b") == 3
        print("SYNONYM_POSTGRESQL_NONE_GREEN")
    engine.dispose()
    print("SYNONYM_POSTGRESQL_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
