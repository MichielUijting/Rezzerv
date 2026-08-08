from __future__ import annotations

import sys
import traceback
from collections.abc import Callable

from sqlalchemy import create_engine, text

from app.services.barcode_identity_service import (
    BarcodeHouseholdArticleLinkError,
    calculate_gtin_check_digit,
    link_household_article_to_matched_product,
)


def _valid_gtin(body: str) -> str:
    return body + str(calculate_gtin_check_digit(body))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    gtin = _valid_gtin("871234567890")

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE global_products "
            "(id TEXT PRIMARY KEY, name TEXT, brand TEXT, "
            "status TEXT, primary_gtin TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE product_identities "
            "(id TEXT PRIMARY KEY, global_product_id TEXT, "
            "identity_type TEXT, identity_value TEXT, "
            "source TEXT, is_primary INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE product_group_memberships "
            "(global_product_id TEXT, inventory_group_key TEXT, "
            "active INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE product_inventory_groups "
            "(inventory_group_key TEXT, gpc_brick_code TEXT, "
            "display_name TEXT, source TEXT, active INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE purchase_import_batches "
            "(batch_id TEXT PRIMARY KEY, household_id TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE purchase_import_lines "
            "(id TEXT PRIMARY KEY, batch_id TEXT, "
            "matched_household_article_id TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE household_articles "
            "(id TEXT PRIMARY KEY, household_id TEXT, "
            "global_product_id TEXT, updated_at TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE inventory_events "
            "(id TEXT PRIMARY KEY)"
        ))

        conn.execute(
            text(
                "INSERT INTO global_products VALUES "
                "('product-1', 'Product', 'Merk', "
                "'active', :gtin)"
            ),
            {"gtin": gtin},
        )
        conn.execute(
            text(
                "INSERT INTO product_identities VALUES "
                "('identity-1', 'product-1', 'gtin', "
                ":gtin, 'manual', 1)"
            ),
            {"gtin": gtin},
        )
        conn.execute(text(
            "INSERT INTO product_group_memberships VALUES "
            "('product-1', 'gpc:10000000', 1)"
        ))
        conn.execute(text(
            "INSERT INTO product_inventory_groups VALUES "
            "('gpc:10000000', '10000000', "
            "'Producttype', 'gs1_gpc_nl', 1)"
        ))
        conn.execute(text(
            "INSERT INTO purchase_import_batches VALUES "
            "('batch-1', 'household-1')"
        ))
        conn.execute(text(
            "INSERT INTO purchase_import_lines VALUES "
            "('line-1', 'batch-1', NULL)"
        ))
        conn.execute(text(
            "INSERT INTO household_articles VALUES "
            "('article-1', 'household-1', NULL, NULL)"
        ))
        conn.execute(text(
            "INSERT INTO household_articles VALUES "
            "('article-other', 'household-2', NULL, NULL)"
        ))

    return engine, gtin


def check_link_and_idempotency() -> None:
    engine, gtin = _database()

    with engine.begin() as conn:
        first = link_household_article_to_matched_product(
            conn,
            household_id="household-1",
            purchase_import_line_id="line-1",
            household_article_id="article-1",
            gtin=gtin,
            global_product_id="product-1",
        )

        second = link_household_article_to_matched_product(
            conn,
            household_id="household-1",
            purchase_import_line_id="line-1",
            household_article_id="article-1",
            gtin=gtin,
            global_product_id="product-1",
        )

        article_product = conn.execute(text(
            "SELECT global_product_id "
            "FROM household_articles "
            "WHERE id = 'article-1'"
        )).scalar_one()

        mapped_article = conn.execute(text(
            "SELECT matched_household_article_id "
            "FROM purchase_import_lines "
            "WHERE id = 'line-1'"
        )).scalar_one()

        events = conn.execute(text(
            "SELECT COUNT(*) FROM inventory_events"
        )).scalar_one()

    _assert(first["changed"] is True, "Eerste koppeling wijzigt niet")
    _assert(second["idempotent"] is True, "Koppeling is niet idempotent")
    _assert(article_product == "product-1", "Product-id niet opgeslagen")
    _assert(mapped_article == "article-1", "Bonregel niet gekoppeld")
    _assert(events == 0, "Er is een voorraad-event aangemaakt")


def check_household_isolation() -> None:
    engine, gtin = _database()

    with engine.begin() as conn:
        try:
            link_household_article_to_matched_product(
                conn,
                household_id="household-1",
                purchase_import_line_id="line-1",
                household_article_id="article-other",
                gtin=gtin,
                global_product_id="product-1",
            )
        except BarcodeHouseholdArticleLinkError as exc:
            _assert(
                exc.status_code == 404,
                "Ander huishouden moet als niet gevonden gelden",
            )
        else:
            raise AssertionError(
                "Artikel uit ander huishouden is gekoppeld"
            )


def check_product_mismatch_rejected() -> None:
    engine, gtin = _database()

    with engine.begin() as conn:
        try:
            link_household_article_to_matched_product(
                conn,
                household_id="household-1",
                purchase_import_line_id="line-1",
                household_article_id="article-1",
                gtin=gtin,
                global_product_id="product-other",
            )
        except BarcodeHouseholdArticleLinkError as exc:
            _assert(
                exc.status_code == 409,
                "Productmismatch moet een conflict geven",
            )
        else:
            raise AssertionError(
                "Productmismatch is geaccepteerd"
            )


def main() -> int:
    checks: list[tuple[str, Callable[[], None]]] = [
        ("Koppeling en idempotentie", check_link_and_idempotency),
        ("Huishoudisolatie", check_household_isolation),
        ("Productmismatch geweigerd", check_product_mismatch_rejected),
    ]

    failures = 0

    print("Rezzerv barcode Fase 3 - contracttests")
    print("=" * 52)

    for number, (name, check) in enumerate(checks, start=1):
        try:
            check()
            print(f"PASS {number}/{len(checks)} - {name}")
        except Exception as exc:
            failures += 1
            print(
                f"FAIL {number}/{len(checks)} - {name}: {exc}"
            )
            traceback.print_exc()

    print("=" * 52)

    if failures:
        print(
            f"RESULTAAT: ROOD - {failures} controle(s) mislukt"
        )
        return 1

    print(
        f"RESULTAAT: GROEN - "
        f"{len(checks)} van {len(checks)} controles geslaagd"
    )
    print("Voorraadmutaties: geen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
