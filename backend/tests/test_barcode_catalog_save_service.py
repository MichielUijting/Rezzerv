from __future__ import annotations

import sys
import traceback
from collections.abc import Callable

from sqlalchemy import create_engine, text

from app.services.barcode_identity_service import (
    calculate_gtin_check_digit,
    save_gtin_catalog_and_household_link,
)


def valid_gtin(body: str) -> str:
    return body + str(calculate_gtin_check_digit(body))


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def build_database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    gtin = valid_gtin("089394000222")

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE global_products ("
            "id TEXT PRIMARY KEY, "
            "name TEXT, brand TEXT, primary_gtin TEXT, "
            "source TEXT, status TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE product_identities ("
            "id TEXT PRIMARY KEY, "
            "global_product_id TEXT, identity_type TEXT, "
            "identity_value TEXT, source TEXT, is_primary INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE purchase_import_batches ("
            "batch_id TEXT PRIMARY KEY, household_id TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE purchase_import_lines ("
            "id TEXT PRIMARY KEY, batch_id TEXT, "
            "matched_household_article_id TEXT, "
            "matched_global_product_id TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE household_articles ("
            "id TEXT PRIMARY KEY, household_id TEXT, "
            "global_product_id TEXT, updated_at TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE inventory_events (id TEXT PRIMARY KEY)"
        ))

        conn.execute(text(
            "INSERT INTO purchase_import_batches "
            "VALUES ('batch-1', 'household-1')"
        ))
        conn.execute(text(
            "INSERT INTO purchase_import_lines "
            "VALUES ('line-1', 'batch-1', NULL, NULL)"
        ))
        conn.execute(text(
            "INSERT INTO household_articles "
            "VALUES ('article-1', 'household-1', NULL, NULL)"
        ))

    return engine, gtin


def check_unknown_gtin_is_created_and_linked() -> None:
    engine, gtin = build_database()

    with engine.begin() as conn:
        result = save_gtin_catalog_and_household_link(
            conn,
            household_id="household-1",
            purchase_import_line_id="line-1",
            household_article_id="article-1",
            gtin=gtin,
            article_name="Apple Quinoa",
        )

        product_count = conn.execute(text(
            "SELECT COUNT(*) FROM global_products"
        )).scalar_one()

        identity_count = conn.execute(text(
            "SELECT COUNT(*) FROM product_identities "
            "WHERE identity_type = 'gtin' "
            "AND identity_value = :gtin"
        ), {"gtin": gtin}).scalar_one()

        article_product = conn.execute(text(
            "SELECT global_product_id "
            "FROM household_articles "
            "WHERE id = 'article-1'"
        )).scalar_one()

        line_product = conn.execute(text(
            "SELECT matched_global_product_id "
            "FROM purchase_import_lines "
            "WHERE id = 'line-1'"
        )).scalar_one()

        event_count = conn.execute(text(
            "SELECT COUNT(*) FROM inventory_events"
        )).scalar_one()

    assert_true(
        result["catalog_product_created"] is True,
        "Centraal product is niet aangemaakt",
    )
    assert_true(product_count == 1, "Onjuist aantal producten")
    assert_true(identity_count == 1, "GTIN-identiteit ontbreekt")
    assert_true(
        article_product == result["product"]["global_product_id"],
        "Huishoudartikel is niet gekoppeld",
    )
    assert_true(
        line_product == result["product"]["global_product_id"],
        "Uitpakken-regel is niet bijgewerkt",
    )
    assert_true(event_count == 0, "Voorraad is gewijzigd")


def check_repeat_is_idempotent() -> None:
    engine, gtin = build_database()

    with engine.begin() as conn:
        first = save_gtin_catalog_and_household_link(
            conn,
            household_id="household-1",
            purchase_import_line_id="line-1",
            household_article_id="article-1",
            gtin=gtin,
            article_name="Apple Quinoa",
        )

        second = save_gtin_catalog_and_household_link(
            conn,
            household_id="household-1",
            purchase_import_line_id="line-1",
            household_article_id="article-1",
            gtin=gtin,
            article_name="Apple Quinoa",
        )

        product_count = conn.execute(text(
            "SELECT COUNT(*) FROM global_products"
        )).scalar_one()

        identity_count = conn.execute(text(
            "SELECT COUNT(*) FROM product_identities"
        )).scalar_one()

    assert_true(
        first["catalog_product_created"] is True,
        "Eerste opslag moet een product maken",
    )
    assert_true(
        second["catalog_product_created"] is False,
        "Tweede opslag mag geen nieuw product maken",
    )
    assert_true(product_count == 1, "Dubbel product aangemaakt")
    assert_true(identity_count == 1, "Dubbele identiteit aangemaakt")


def main() -> int:
    checks: list[tuple[str, Callable[[], None]]] = [
        (
            "Onbekende GTIN wordt centraal en lokaal opgeslagen",
            check_unknown_gtin_is_created_and_linked,
        ),
        (
            "Herhaalde opslag is idempotent",
            check_repeat_is_idempotent,
        ),
    ]

    failures = 0

    print("Rezzerv Fase 3 - catalogusopslagcontracttests")
    print("=" * 62)

    for number, (name, check) in enumerate(checks, start=1):
        try:
            check()
            print(f"PASS {number}/{len(checks)} - {name}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {number}/{len(checks)} - {name}: {exc}")
            traceback.print_exc()

    print("=" * 62)

    if failures:
        print(f"RESULTAAT: ROOD - {failures} controle(s) mislukt")
        return 1

    print(
        f"RESULTAAT: GROEN - "
        f"{len(checks)} van {len(checks)} controles geslaagd"
    )
    print("Voorraadmutaties: geen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
