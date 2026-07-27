from __future__ import annotations

import sys
import traceback
from collections.abc import Callable

from sqlalchemy import create_engine, text

from app.services.barcode_identity_service import calculate_gtin_check_digit
from app.services.generic_product_link_replacement_service import (
    GENERIC_REPLACEMENT_BLOCKED,
    REPLACEMENT_CONFIRMATION_REQUIRED,
    GenericProductLinkReplacementError,
    replace_generic_household_article_product_link,
)


def _valid_gtin(body: str) -> str:
    return body + str(calculate_gtin_check_digit(body))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _database(*, current_specific: bool = False):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    requested_gtin = _valid_gtin("731010069484")
    current_gtin = _valid_gtin("871234567890") if current_specific else None

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE global_products ("
            "id TEXT PRIMARY KEY, name TEXT, brand TEXT, status TEXT, "
            "primary_gtin TEXT, source TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE product_identities ("
            "id TEXT PRIMARY KEY, global_product_id TEXT, identity_type TEXT, "
            "identity_value TEXT, source TEXT, is_primary INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE product_group_memberships ("
            "global_product_id TEXT, inventory_group_key TEXT, active INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE product_inventory_groups ("
            "inventory_group_key TEXT, gpc_brick_code TEXT, display_name TEXT, "
            "source TEXT, active INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE purchase_import_batches ("
            "batch_id TEXT PRIMARY KEY, household_id TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE purchase_import_lines ("
            "id TEXT PRIMARY KEY, batch_id TEXT, "
            "matched_household_article_id TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE household_articles ("
            "id TEXT PRIMARY KEY, household_id TEXT, global_product_id TEXT, "
            "article_group_id TEXT, min_stock REAL, ideal_stock REAL, "
            "notes TEXT, updated_at TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE inventory ("
            "id TEXT PRIMARY KEY, household_article_id TEXT, quantity REAL, "
            "space_id TEXT, sublocation_id TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE inventory_events ("
            "id TEXT PRIMARY KEY, inventory_id TEXT, event_type TEXT)"
        ))

        conn.execute(
            text(
                "INSERT INTO global_products VALUES "
                "('generic-product', 'Pizza', NULL, 'active', :current_gtin, 'user')"
            ),
            {"current_gtin": current_gtin},
        )
        conn.execute(
            text(
                "INSERT INTO global_products VALUES "
                "('organix-product', 'Organix Kids Llama Puffs Pizza', "
                "'Organix', 'active', :gtin, 'openfoodfacts')"
            ),
            {"gtin": requested_gtin},
        )
        conn.execute(
            text(
                "INSERT INTO product_identities VALUES "
                "('organix-identity', 'organix-product', 'gtin', :gtin, "
                "'openfoodfacts', 1)"
            ),
            {"gtin": requested_gtin},
        )
        if current_specific:
            conn.execute(
                text(
                    "INSERT INTO product_identities VALUES "
                    "('generic-identity', 'generic-product', 'gtin', :gtin, "
                    "'manual', 1)"
                ),
                {"gtin": current_gtin},
            )

        conn.execute(text(
            "INSERT INTO product_group_memberships VALUES "
            "('organix-product', 'gpc:10000177', 1)"
        ))
        conn.execute(text(
            "INSERT INTO product_inventory_groups VALUES "
            "('gpc:10000177', '10000177', 'Chips/Crisps/Snack Mixes', "
            "'gs1_gpc_2026_05_en', 1)"
        ))
        conn.execute(text(
            "INSERT INTO purchase_import_batches VALUES "
            "('batch-1', 'household-1')"
        ))
        conn.execute(text(
            "INSERT INTO purchase_import_lines VALUES "
            "('line-1', 'batch-1', 'article-1')"
        ))
        conn.execute(text(
            "INSERT INTO household_articles VALUES "
            "('article-1', 'household-1', 'generic-product', 'group-7', "
            "2, 5, 'bewaren', NULL)"
        ))
        conn.execute(text(
            "INSERT INTO household_articles VALUES "
            "('article-other', 'household-2', 'generic-product', 'group-8', "
            "1, 2, 'ander huishouden', NULL)"
        ))
        conn.execute(text(
            "INSERT INTO inventory VALUES "
            "('inventory-1', 'article-1', 3, 'space-1', 'sub-1')"
        ))
        conn.execute(text(
            "INSERT INTO inventory_events VALUES "
            "('event-1', 'inventory-1', 'purchase')"
        ))

    return engine, requested_gtin


def _call(conn, gtin: str, *, confirm: bool = False, article_id: str = "article-1"):
    return replace_generic_household_article_product_link(
        conn,
        household_id="household-1",
        purchase_import_line_id="line-1",
        household_article_id=article_id,
        gtin=gtin,
        global_product_id="organix-product",
        confirm_replace_generic_link=confirm,
    )


def check_confirmation_required_without_mutation() -> None:
    engine, gtin = _database()
    with engine.begin() as conn:
        before = conn.execute(text(
            "SELECT global_product_id FROM household_articles WHERE id = 'article-1'"
        )).scalar_one()
        try:
            _call(conn, gtin)
        except GenericProductLinkReplacementError as exc:
            _assert(exc.status_code == 409, "Bevestigingsvraag moet HTTP 409 zijn")
            _assert(isinstance(exc.detail, dict), "Detail moet gestructureerd zijn")
            _assert(
                exc.detail.get("code") == REPLACEMENT_CONFIRMATION_REQUIRED,
                "Verkeerde foutcode voor bevestigingsvraag",
            )
            _assert(exc.detail.get("replacement_allowed") is True, "Vervanging niet toegestaan")
            _assert(
                (exc.detail.get("current_product") or {}).get("name") == "Pizza",
                "Huidig product ontbreekt in respons",
            )
        else:
            raise AssertionError("Generieke koppeling is zonder bevestiging vervangen")
        after = conn.execute(text(
            "SELECT global_product_id FROM household_articles WHERE id = 'article-1'"
        )).scalar_one()
    _assert(before == after == "generic-product", "Koppeling wijzigde zonder bevestiging")


def check_confirmed_replacement_preserves_household_data() -> None:
    engine, gtin = _database()
    with engine.begin() as conn:
        article_before = conn.execute(text(
            "SELECT article_group_id, min_stock, ideal_stock, notes "
            "FROM household_articles WHERE id = 'article-1'"
        )).mappings().one()
        inventory_before = conn.execute(text(
            "SELECT quantity, space_id, sublocation_id FROM inventory "
            "WHERE household_article_id = 'article-1'"
        )).mappings().one()
        events_before = conn.execute(text(
            "SELECT COUNT(*) FROM inventory_events"
        )).scalar_one()

        result = _call(conn, gtin, confirm=True)

        article_after = conn.execute(text(
            "SELECT global_product_id, article_group_id, min_stock, ideal_stock, notes "
            "FROM household_articles WHERE id = 'article-1'"
        )).mappings().one()
        inventory_after = conn.execute(text(
            "SELECT quantity, space_id, sublocation_id FROM inventory "
            "WHERE household_article_id = 'article-1'"
        )).mappings().one()
        events_after = conn.execute(text(
            "SELECT COUNT(*) FROM inventory_events"
        )).scalar_one()
        mapped_article = conn.execute(text(
            "SELECT matched_household_article_id FROM purchase_import_lines "
            "WHERE id = 'line-1'"
        )).scalar_one()
        old_product_exists = conn.execute(text(
            "SELECT COUNT(*) FROM global_products WHERE id = 'generic-product'"
        )).scalar_one()

    _assert(result["changed"] is True, "Vervanging is niet als wijziging gemeld")
    _assert(result["inventory_mutated"] is False, "Voorraadmutatie onjuist gemeld")
    _assert(article_after["global_product_id"] == "organix-product", "Nieuw product niet gekoppeld")
    _assert(
        tuple(article_before.values()) == tuple(
            article_after[key] for key in ("article_group_id", "min_stock", "ideal_stock", "notes")
        ),
        "Huishoudspecifieke artikeldata is gewijzigd",
    )
    _assert(dict(inventory_before) == dict(inventory_after), "Voorraad of locatie is gewijzigd")
    _assert(events_before == events_after == 1, "Inventory-events zijn gewijzigd")
    _assert(mapped_article == "article-1", "Bonregel verloor huishoudartikelkoppeling")
    _assert(old_product_exists == 1, "Oud generiek product is verwijderd")


def check_specific_existing_product_is_blocked() -> None:
    engine, gtin = _database(current_specific=True)
    with engine.begin() as conn:
        try:
            _call(conn, gtin, confirm=True)
        except GenericProductLinkReplacementError as exc:
            _assert(exc.status_code == 409, "Specifieke koppeling moet conflict geven")
            _assert(
                isinstance(exc.detail, dict)
                and exc.detail.get("code") == GENERIC_REPLACEMENT_BLOCKED,
                "Specifieke koppeling gaf verkeerde foutcode",
            )
            _assert(exc.detail.get("replacement_allowed") is False, "Specifieke koppeling is vervangbaar")
        else:
            raise AssertionError("Specifieke koppeling is overschreven")


def check_household_isolation() -> None:
    engine, gtin = _database()
    with engine.begin() as conn:
        try:
            _call(conn, gtin, confirm=True, article_id="article-other")
        except GenericProductLinkReplacementError as exc:
            _assert(exc.status_code == 404, "Ander huishouden moet als niet gevonden gelden")
        else:
            raise AssertionError("Artikel uit ander huishouden is gewijzigd")


def main() -> int:
    checks: list[tuple[str, Callable[[], None]]] = [
        ("Bevestiging vereist zonder mutatie", check_confirmation_required_without_mutation),
        ("Bevestigde vervanging behoudt data", check_confirmed_replacement_preserves_household_data),
        ("Specifieke koppeling blijft beschermd", check_specific_existing_product_is_blocked),
        ("Huishoudisolatie", check_household_isolation),
    ]

    failures = 0
    print("Rezzerv generieke productkoppeling - backendcontracttests")
    print("=" * 64)
    for number, (name, check) in enumerate(checks, start=1):
        try:
            check()
            print(f"PASS {number}/{len(checks)} - {name}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {number}/{len(checks)} - {name}: {exc}")
            traceback.print_exc()

    print("=" * 64)
    if failures:
        print(f"RESULTAAT: ROOD - {failures} controle(s) mislukt")
        return 1
    print(f"RESULTAAT: GROEN - {len(checks)} van {len(checks)} controles geslaagd")
    print("Voorraadmutaties: geen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
