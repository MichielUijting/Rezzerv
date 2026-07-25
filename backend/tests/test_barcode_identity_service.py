"""Standalone contract tests for the central Rezzerv barcode service.

Run inside the backend container with:
    python /app/tests/test_barcode_identity_service.py

No pytest dependency is required.
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable

from sqlalchemy import create_engine, text

from app.services.barcode_identity_service import (
    calculate_gtin_check_digit,
    lookup_gtin,
    validate_barcode,
)


def _valid_gtin(body: str) -> str:
    return body + str(calculate_gtin_check_digit(body))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_supported_gtin_lengths_and_check_digit() -> None:
    for body in ("1234567", "12345678901", "123456789012", "1234567890123"):
        result = validate_barcode(_valid_gtin(body), "gtin")
        _assert(result["valid"] is True, f"Geldige GTIN afgekeurd: {body}")
        _assert(result["mutated"] is False, "Validatie mag niets muteren")

    for length in (7, 9, 10, 11, 15):
        result = validate_barcode("1" * length, "gtin")
        _assert(result["valid"] is False, f"Ongeldige GTIN-lengte {length} geaccepteerd")
        _assert(
            any(error["code"] == "INVALID_GTIN_LENGTH" for error in result["errors"]),
            f"Foutcode INVALID_GTIN_LENGTH ontbreekt voor lengte {length}",
        )


def check_invalid_check_digit_and_non_numeric_gtin() -> None:
    valid = _valid_gtin("871234567890")
    wrong = valid[:-1] + str((int(valid[-1]) + 1) % 10)
    _assert(validate_barcode(wrong, "gtin")["valid"] is False, "Ongeldig controlecijfer geaccepteerd")
    _assert(validate_barcode("8712ABC678906", "gtin")["valid"] is False, "Niet-numerieke GTIN geaccepteerd")


def check_retailer_article_number_is_not_promoted_to_gtin() -> None:
    result = validate_barcode("8712345678906", "retailer_article_number")
    _assert(result["valid"] is True, "Winkelartikelcode is ten onrechte ongeldig")
    _assert(result["identity_type"] == "retailer_article_number", "Identiteitstype is gewijzigd")
    _assert(result["gtin_format"] is None, "Winkelartikelcode is als GTIN geclassificeerd")
    _assert(result["validation"]["check_digit_valid"] is None, "GTIN-check is ten onrechte uitgevoerd")


def check_lookup_is_read_only_and_reports_complete_product() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    gtin = _valid_gtin("871234567890")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE global_products (id TEXT PRIMARY KEY, name TEXT, brand TEXT, status TEXT, primary_gtin TEXT)"))
        conn.execute(text("CREATE TABLE product_identities (id TEXT PRIMARY KEY, global_product_id TEXT, identity_type TEXT, identity_value TEXT, source TEXT, is_primary INTEGER)"))
        conn.execute(text("CREATE TABLE product_group_memberships (global_product_id TEXT, inventory_group_key TEXT, active INTEGER)"))
        conn.execute(text("CREATE TABLE product_inventory_groups (inventory_group_key TEXT, gpc_brick_code TEXT, display_name TEXT, source TEXT, active INTEGER)"))
        conn.execute(text("CREATE TABLE inventory_events (id TEXT PRIMARY KEY)"))
        conn.execute(text("INSERT INTO global_products VALUES ('product-1', 'Product', 'Merk', 'active', :gtin)"), {"gtin": gtin})
        conn.execute(text("INSERT INTO product_identities VALUES ('identity-1', 'product-1', 'gtin', :gtin, 'manual', 1)"), {"gtin": gtin})
        conn.execute(text("INSERT INTO product_group_memberships VALUES ('product-1', 'gpc:10000000', 1)"))
        conn.execute(text("INSERT INTO product_inventory_groups VALUES ('gpc:10000000', '10000000', 'Producttype', 'gs1_gpc_en', 1)"))
        before = conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar_one()
        result = lookup_gtin(conn, gtin)
        after = conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar_one()

    _assert(result["match_status"] == "matched", "Compleet product is niet als matched gemeld")
    _assert(result["product"]["global_product_id"] == "product-1", "Verkeerd product gevonden")
    _assert(result["quality"]["official_gpc_active"] is True, "Officieel actief GPC-type niet herkend")
    _assert(result["mutated"] is False, "Lookup mag niets muteren")
    _assert(before == after == 0, "Lookup heeft een voorraad-event aangemaakt")


def check_lookup_reports_incomplete_without_identity_or_official_gpc() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    gtin = _valid_gtin("123456789012")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE global_products (id TEXT PRIMARY KEY, name TEXT, brand TEXT, status TEXT, primary_gtin TEXT)"))
        conn.execute(text("CREATE TABLE product_identities (id TEXT PRIMARY KEY, global_product_id TEXT, identity_type TEXT, identity_value TEXT, source TEXT, is_primary INTEGER)"))
        conn.execute(text("INSERT INTO global_products VALUES ('product-1', 'Product', NULL, 'active', :gtin)"), {"gtin": gtin})
        result = lookup_gtin(conn, gtin)

    _assert(result["match_status"] == "incomplete", "Onvolledig product is niet als incomplete gemeld")
    _assert(result["quality"]["identity_consistent"] is False, "Ontbrekende GTIN-identiteit niet gesignaleerd")
    _assert(result["quality"]["official_gpc_active"] is False, "Ontbrekend officieel GPC-type niet gesignaleerd")


def main() -> int:
    checks: list[tuple[str, Callable[[], None]]] = [
        ("GTIN-lengtes en controlecijfer", check_supported_gtin_lengths_and_check_digit),
        ("Ongeldig controlecijfer en niet-numerieke GTIN", check_invalid_check_digit_and_non_numeric_gtin),
        ("Winkelartikelcode blijft apart", check_retailer_article_number_is_not_promoted_to_gtin),
        ("Lookup is read-only en compleet", check_lookup_is_read_only_and_reports_complete_product),
        ("Onvolledige productkoppeling wordt gemeld", check_lookup_reports_incomplete_without_identity_or_official_gpc),
    ]

    print("Rezzerv barcode Fase 1 - contracttests")
    print("=" * 52)
    failures = 0
    for number, (name, check) in enumerate(checks, start=1):
        try:
            check()
            print(f"PASS {number}/5 - {name}")
        except Exception as exc:  # noqa: BLE001 - standalone test runner must report every failure
            failures += 1
            print(f"FAIL {number}/5 - {name}: {exc}")
            traceback.print_exc()

    print("=" * 52)
    if failures:
        print(f"RESULTAAT: ROOD - {failures} van 5 controles mislukt")
        return 1

    print("RESULTAAT: GROEN - 5 van 5 controles geslaagd")
    print("Mutaties: geen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
