from __future__ import annotations

import inspect
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text

from app import main


HOUSEHOLD_ID = "0"
ARTICLE_ID = "hh0-ah-bananen"
ARTICLE_NAME = "AH BANANEN"
SPACE_ID = "hh0-keuken"
SUBLOCATION_ID = "hh0-fruitschaal"
PURCHASE_DATE = "2019-05-11"

LOCATION = {
    "space_id": SPACE_ID,
    "space_name": "Keuken",
    "sublocation_id": SUBLOCATION_ID,
    "sublocation_name": "Fruitschaal",
    "location_id": SUBLOCATION_ID,
    "location_label": "Keuken / Fruitschaal",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


def create_schema(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                naam TEXT NOT NULL,
                custom_name TEXT,
                consumable INTEGER NOT NULL DEFAULT 0,
                source TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE inventory (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                household_article_id TEXT,
                naam TEXT NOT NULL,
                aantal INTEGER NOT NULL,
                space_id TEXT,
                sublocation_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                article_id TEXT,
                household_article_id TEXT,
                article_name TEXT NOT NULL,
                location_id TEXT,
                location_label TEXT,
                event_type TEXT NOT NULL,
                quantity NUMERIC NOT NULL,
                old_quantity NUMERIC,
                new_quantity NUMERIC,
                source TEXT NOT NULL,
                note TEXT,
                purchase_date TEXT,
                supplier_name TEXT,
                article_number TEXT,
                price NUMERIC,
                currency TEXT,
                barcode TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def seed_article(conn, *, consumable: bool = True) -> None:
    conn.execute(
        text(
            """
            INSERT INTO household_articles (
                id, household_id, naam, custom_name, consumable,
                source, status, created_at, updated_at
            ) VALUES (
                :id, :household_id, :naam, NULL, :consumable,
                'regression_household_0', 'active',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": ARTICLE_ID,
            "household_id": HOUSEHOLD_ID,
            "naam": ARTICLE_NAME,
            "consumable": 1 if consumable else 0,
        },
    )


def seed_existing_inventory(conn, quantity: int) -> str:
    inventory_id = "hh0-existing-bananen"

    conn.execute(
        text(
            """
            INSERT INTO inventory (
                id, household_id, household_article_id, naam, aantal,
                space_id, sublocation_id, status,
                created_at, updated_at
            ) VALUES (
                :id, :household_id, :household_article_id, :naam, :aantal,
                :space_id, :sublocation_id, 'active',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": inventory_id,
            "household_id": HOUSEHOLD_ID,
            "household_article_id": ARTICLE_ID,
            "naam": ARTICLE_NAME,
            "aantal": quantity,
            "space_id": SPACE_ID,
            "sublocation_id": SUBLOCATION_ID,
        },
    )

    return inventory_id


def inventory_total(conn) -> int:
    return int(
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
            {
                "household_id": HOUSEHOLD_ID,
                "article_id": ARTICLE_ID,
            },
        ).scalar()
        or 0
    )


def inventory_quantity(conn, inventory_id: str) -> int:
    return int(
        conn.execute(
            text("SELECT COALESCE(aantal, 0) FROM inventory WHERE id = :id"),
            {"id": inventory_id},
        ).scalar()
        or 0
    )


def event_rows(conn) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            text(
                """
                SELECT
                    household_id,
                    event_type,
                    quantity,
                    old_quantity,
                    new_quantity,
                    purchase_date,
                    created_at
                FROM inventory_events
                ORDER BY created_at ASC, event_type ASC
                """
            )
        ).mappings()
    ]


def run_inventory_scenario(
    conn,
    *,
    mode: str,
    existing_quantity: int,
    purchased_quantity: int,
) -> dict:
    existing_inventory_id = seed_existing_inventory(conn, existing_quantity)

    pre_purchase_total = inventory_total(conn)

    requested = main.compute_auto_deduction_quantity(
        mode,
        pre_purchase_total,
        purchased_quantity,
    )

    purchase_event_id = main.create_inventory_purchase_event(
        conn,
        HOUSEHOLD_ID,
        ARTICLE_ID,
        ARTICLE_NAME,
        purchased_quantity,
        LOCATION,
        "Regressietest huishouden 0",
        supplier_name="Albert Heijn",
        purchase_date=PURCHASE_DATE,
        article_number="AH-BANANEN-TEST",
        currency="EUR",
    )

    purchase_inventory_id = main.apply_inventory_purchase(
        conn,
        HOUSEHOLD_ID,
        ARTICLE_NAME,
        purchased_quantity,
        LOCATION,
    )

    auto_event_id = None
    applied = 0

    if requested > 0:
        auto_event_id = main.create_auto_repurchase_event(
            conn,
            HOUSEHOLD_ID,
            ARTICLE_ID,
            ARTICLE_NAME,
            LOCATION,
            quantity=requested,
            purchase_date=PURCHASE_DATE,
        )

        result = main.apply_inventory_consumption(
            conn,
            HOUSEHOLD_ID,
            ARTICLE_NAME,
            requested,
            LOCATION,
            mode=mode,
            protected_quantity_on_purchase_row=purchased_quantity,
            protected_purchase_inventory_id=purchase_inventory_id,
        )

        applied = int(result.get("applied_quantity") or 0)

    return {
        "pre_purchase_total": pre_purchase_total,
        "requested": requested,
        "applied": applied,
        "purchase_event_id": purchase_event_id,
        "auto_event_id": auto_event_id,
        "existing_inventory_id": existing_inventory_id,
        "purchase_inventory_id": purchase_inventory_id,
        "final_total": inventory_total(conn),
        "events": event_rows(conn),
    }


def scenario_effective_mode_resolution() -> None:
    none = main.ARTICLE_AUTO_CONSUME_NONE
    purchased = main.ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY
    all_existing = main.ARTICLE_AUTO_CONSUME_ALL_EXISTING
    follow = main.ARTICLE_AUTO_CONSUME_FOLLOW_HOUSEHOLD

    require(
        main.resolve_auto_consume_effective_mode(
            purchased,
            follow,
            False,
        )
        == none,
        "niet-verbruiksartikel wordt nooit automatisch afgeboekt",
    )

    require(
        main.resolve_auto_consume_effective_mode(
            purchased,
            none,
            True,
        )
        == none,
        "artikelafwijking 'geen' overschrijft huishoudstrategie",
    )

    require(
        main.resolve_auto_consume_effective_mode(
            none,
            purchased,
            True,
        )
        == purchased,
        "artikelafwijking 'gekochte hoeveelheid' overschrijft huishouden",
    )

    require(
        main.resolve_auto_consume_effective_mode(
            none,
            all_existing,
            True,
        )
        == all_existing,
        "artikelafwijking 'alle bestaande voorraad' overschrijft huishouden",
    )


def scenario_no_automatic_deduction(conn) -> None:
    result = run_inventory_scenario(
        conn,
        mode=main.ARTICLE_AUTO_CONSUME_NONE,
        existing_quantity=3,
        purchased_quantity=2,
    )

    require(result["requested"] == 0, "strategie geen vraagt geen afboeking")
    require(result["applied"] == 0, "strategie geen boekt niets af")
    require(result["final_total"] == 5, "voorraad wordt alleen met aankoop verhoogd")
    require(result["auto_event_id"] is None, "geen automatisch afboekingsevent aangemaakt")
    require(len(result["events"]) == 1, "alleen inkoopevent aanwezig")


def scenario_purchased_quantity(conn) -> None:
    result = run_inventory_scenario(
        conn,
        mode=main.ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY,
        existing_quantity=3,
        purchased_quantity=2,
    )

    require(result["requested"] == 2, "gekochte hoeveelheid vraagt afboeking van twee")
    require(result["applied"] == 2, "twee bestaande eenheden zijn afgeboekt")
    require(result["final_total"] == 3, "eindvoorraad is drie")
    require(
        result["existing_inventory_id"] == result["purchase_inventory_id"],
        "aankoop is volgens het voorraadmodel samengevoegd met de bestaande regel",
    )
    require(
        inventory_quantity(conn, result["purchase_inventory_id"]) == 3,
        "samengevoegde voorraadregel eindigt op drie",
    )
    require(
        inventory_quantity(conn, result["purchase_inventory_id"]) >= 2,
        "minimaal de nieuw gekochte hoeveelheid blijft beschermd",
    )
    require(result["auto_event_id"] is not None, "automatisch afboekingsevent bestaat")


def scenario_all_existing(conn) -> None:
    result = run_inventory_scenario(
        conn,
        mode=main.ARTICLE_AUTO_CONSUME_ALL_EXISTING,
        existing_quantity=3,
        purchased_quantity=2,
    )

    require(result["requested"] == 3, "alle bestaande voorraad vraagt afboeking van drie")
    require(result["applied"] == 3, "alle drie oude eenheden zijn afgeboekt")
    require(result["final_total"] == 2, "alleen de nieuwe aankoop blijft over")
    require(
        result["existing_inventory_id"] == result["purchase_inventory_id"],
        "aankoop is ook bij deze strategie samengevoegd met de bestaande regel",
    )
    require(
        inventory_quantity(conn, result["purchase_inventory_id"]) == 2,
        "na afboeking van alle eerdere voorraad blijft alleen de aankoop over",
    )


def scenario_purchase_date_and_technical_time(conn) -> None:
    result = run_inventory_scenario(
        conn,
        mode=main.ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY,
        existing_quantity=3,
        purchased_quantity=2,
    )

    require(len(result["events"]) == 2, "inkoop- en afboekingsevent zijn aanwezig")

    event_types = {row["event_type"] for row in result["events"]}

    require(
        event_types == {"purchase", "auto_repurchase"},
        "juiste twee eventtypen zijn opgeslagen",
    )

    for row in result["events"]:
        require(
            row["household_id"] == HOUSEHOLD_ID,
            f"{row['event_type']} hoort uitsluitend bij huishouden 0",
        )
        require(
            row["purchase_date"] == PURCHASE_DATE,
            f"{row['event_type']} gebruikt de aankoopdatum",
        )
        require(
            str(row["created_at"] or "")[:10] != PURCHASE_DATE,
            f"{row['event_type']} houdt technische tijd apart",
        )


def scenario_process_chain_contract() -> None:
    source = inspect.getsource(main.process_purchase_import_batch)

    require(
        "determine_auto_consume_decision(" in source,
        "productieverwerking gebruikt centrale strategiebeslissing",
    )
    require(
        "create_inventory_purchase_event(" in source,
        "productieverwerking maakt het inkoopevent",
    )
    require(
        "create_auto_repurchase_event(" in source,
        "productieverwerking maakt zo nodig het afboekingsevent",
    )
    require(
        "apply_inventory_consumption(" in source,
        "productieverwerking muteert de werkelijke voorraad",
    )
    require(
        "protected_purchase_inventory_id=purchase_inventory_id" in source,
        "productieverwerking beschermt de nieuwe aankoop",
    )
    require(
        "purchase_date=purchase_date" in source,
        "productieverwerking geeft aankoopdatum door",
    )


def run_isolated_database_scenario(scenario) -> None:
    with tempfile.TemporaryDirectory(
        prefix="rezzerv-household-0-auto-consume-"
    ) as temp_dir:
        database_path = Path(temp_dir) / "regression.sqlite"
        engine = create_engine(f"sqlite:///{database_path}")

        with engine.begin() as conn:
            create_schema(conn)
            seed_article(conn, consumable=True)
            scenario(conn)

            household_ids = {
                str(value)
                for value in conn.execute(
                    text(
                        """
                        SELECT household_id FROM household_articles
                        UNION
                        SELECT household_id FROM inventory
                        UNION
                        SELECT household_id FROM inventory_events
                        """
                    )
                ).scalars()
                if value is not None
            }

            require(
                household_ids <= {HOUSEHOLD_ID},
                "tijdelijke regressiedatabase bevat uitsluitend huishouden 0",
            )

        engine.dispose()

        require(
            database_path.exists(),
            "tijdelijke database bestond tijdens de regressietest",
        )

    require(
        not database_path.exists(),
        "tijdelijke regressiedatabase is automatisch verwijderd",
    )


def main_test() -> None:
    print("REGRESSIESET: automatische voorraadafboeking huishouden 0")
    print("Artikel: AH BANANEN")
    print("Locatie: Keuken / Fruitschaal")
    print("")

    scenario_effective_mode_resolution()
    scenario_process_chain_contract()

    run_isolated_database_scenario(scenario_no_automatic_deduction)
    run_isolated_database_scenario(scenario_purchased_quantity)
    run_isolated_database_scenario(scenario_all_existing)
    run_isolated_database_scenario(scenario_purchase_date_and_technical_time)

    print("")
    print("HOUSEHOLD_ZERO_AUTO_CONSUME_REGRESSION=PASS")


if __name__ == "__main__":
    main_test()
