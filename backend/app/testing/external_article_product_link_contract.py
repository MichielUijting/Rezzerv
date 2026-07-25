"""Geïsoleerde contracttest voor algemene winkelartikelkoppelingen.

Draait op een tijdelijke SQLite-database en raakt geen normale runtime-data.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.external_article_product_link_domain_service import (
    confirm_global_external_article_product_link,
    deactivate_global_external_article_product_link,
    find_global_external_article_product_link,
)
from app.services.external_article_product_link_service import (
    deactivate_incomplete_confirmed_external_links,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _expect_value_error(callable_value, expected_text: str) -> None:
    try:
        callable_value()
    except ValueError as exc:
        _assert(
            expected_text in str(exc),
            f"Verkeerde foutmelding: {exc}",
        )
    else:
        raise AssertionError(
            f"Verwachte ValueError ontbreekt: {expected_text}"
        )


def _create_test_database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE global_products (
                    id TEXT PRIMARY KEY,
                    primary_gtin TEXT,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE product_identities (
                    id TEXT PRIMARY KEY,
                    global_product_id TEXT,
                    identity_type TEXT NOT NULL,
                    identity_value TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE product_inventory_groups (
                    inventory_group_key TEXT PRIMARY KEY,
                    gpc_brick_code TEXT,
                    source TEXT,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE product_group_memberships (
                    id TEXT PRIMARY KEY,
                    global_product_id TEXT NOT NULL,
                    inventory_group_key TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO global_products (
                    id,
                    primary_gtin,
                    name,
                    status
                ) VALUES
                    (
                        'product-a',
                        '8710000000001',
                        'Volledig artikel A',
                        'active'
                    ),
                    (
                        'product-b',
                        '8710000000002',
                        'Volledig artikel B',
                        'active'
                    ),
                    (
                        'product-no-gtin',
                        NULL,
                        'Artikel zonder GTIN',
                        'active'
                    ),
                    (
                        'product-no-identity',
                        '8710000000003',
                        'Artikel zonder GTIN-identiteit',
                        'active'
                    ),
                    (
                        'product-no-gpc',
                        '8710000000004',
                        'Artikel zonder GPC',
                        'active'
                    ),
                    (
                        'product-inactive',
                        '8710000000005',
                        'Inactief Product',
                        'inactive'
                    )
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO product_identities (
                    id,
                    global_product_id,
                    identity_type,
                    identity_value
                ) VALUES
                    (
                        'identity-a',
                        'product-a',
                        'gtin',
                        '8710000000001'
                    ),
                    (
                        'identity-b',
                        'product-b',
                        'gtin',
                        '8710000000002'
                    ),
                    (
                        'identity-no-gpc',
                        'product-no-gpc',
                        'gtin',
                        '8710000000004'
                    ),
                    (
                        'identity-inactive',
                        'product-inactive',
                        'gtin',
                        '8710000000005'
                    )
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO product_inventory_groups (
                    inventory_group_key,
                    gpc_brick_code,
                    source,
                    active
                ) VALUES (
                    'gpc:10000001',
                    '10000001',
                    'gs1_gpc_contract_test',
                    1
                )
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO product_group_memberships (
                    id,
                    global_product_id,
                    inventory_group_key,
                    active
                ) VALUES
                    (
                        'membership-a',
                        'product-a',
                        'gpc:10000001',
                        1
                    ),
                    (
                        'membership-b',
                        'product-b',
                        'gpc:10000001',
                        1
                    ),
                    (
                        'membership-no-identity',
                        'product-no-identity',
                        'gpc:10000001',
                        1
                    ),
                    (
                        'membership-inactive',
                        'product-inactive',
                        'gpc:10000001',
                        1
                    )
                """
            )
        )

    return engine


def run_contract() -> None:
    engine = _create_test_database()

    with engine.begin() as conn:
        first = confirm_global_external_article_product_link(
            conn,
            retailer_code="ALDI",
            receipt_text="VOLLEDIG ARTIKEL",
            global_product_id="product-a",
            confirmed_by="contract-test",
        )
        _assert(
            first["retailer_code"] == "aldi",
            "Winkelcode is niet canoniek opgeslagen",
        )
        _assert(
            first["receipt_text_normalized"] == "volledig artikel",
            "Bontekst is niet canoniek opgeslagen",
        )

        found = find_global_external_article_product_link(
            conn,
            retailer_code="Aldi",
            receipt_text="volledig artikel",
        )
        _assert(
            found is not None,
            "Algemene koppeling is niet teruggevonden",
        )
        _assert(
            found["global_product_id"] == "product-a",
            "Verkeerd universeel artikel gevonden",
        )

        other_retailer = find_global_external_article_product_link(
            conn,
            retailer_code="LIDL",
            receipt_text="VOLLEDIG ARTIKEL",
        )
        _assert(
            other_retailer is None,
            "Koppeling lekt naar een andere winkelketen",
        )

        replacement = confirm_global_external_article_product_link(
            conn,
            retailer_code="aldi",
            receipt_text="volledig artikel",
            global_product_id="product-b",
            confirmed_by="contract-test-correction",
        )
        _assert(
            replacement["global_product_id"] == "product-b",
            "Vervanging is niet opgeslagen",
        )

        counts = conn.execute(
            text(
                """
                SELECT
                    SUM(
                        CASE
                            WHEN status = 'confirmed' THEN 1
                            ELSE 0
                        END
                    ) AS active_count,
                    SUM(
                        CASE
                            WHEN status = 'inactive' THEN 1
                            ELSE 0
                        END
                    ) AS inactive_count
                FROM external_article_product_links
                WHERE retailer_code = 'aldi'
                  AND receipt_text_normalized = 'volledig artikel'
                """
            )
        ).mappings().one()

        _assert(
            int(counts["active_count"] or 0) == 1,
            "Er is niet precies één actieve koppeling",
        )
        _assert(
            int(counts["inactive_count"] or 0) == 1,
            "De vervangen koppeling is niet als historie bewaard",
        )

        confirm_global_external_article_product_link(
            conn,
            retailer_code="ALDI",
            receipt_text="Code heeft voorrang",
            external_article_code=" 123 456 ",
            global_product_id="product-a",
            confirmed_by="contract-test-code",
        )

        by_code = find_global_external_article_product_link(
            conn,
            retailer_code="aldi",
            receipt_text="een andere tekst",
            external_article_code="123456",
        )
        _assert(
            by_code is not None,
            "Koppeling op winkelartikelcode is niet gevonden",
        )
        _assert(
            by_code["global_product_id"] == "product-a",
            "Artikelcode vond verkeerd product",
        )

        _expect_value_error(
            lambda: confirm_global_external_article_product_link(
                conn,
                retailer_code="aldi",
                receipt_text="Geen GTIN",
                global_product_id="product-no-gtin",
            ),
            "geldige GTIN/EAN ontbreekt",
        )

        _expect_value_error(
            lambda: confirm_global_external_article_product_link(
                conn,
                retailer_code="aldi",
                receipt_text="Geen identiteit",
                global_product_id="product-no-identity",
            ),
            "bijpassende GTIN-identiteit ontbreekt",
        )

        _expect_value_error(
            lambda: confirm_global_external_article_product_link(
                conn,
                retailer_code="aldi",
                receipt_text="Geen GPC",
                global_product_id="product-no-gpc",
            ),
            "officieel GS1 GPC-Producttype ontbreekt",
        )

        _expect_value_error(
            lambda: confirm_global_external_article_product_link(
                conn,
                retailer_code="aldi",
                receipt_text="Inactief",
                global_product_id="product-inactive",
            ),
            "niet actief",
        )

        conn.execute(
            text(
                """
                INSERT INTO external_article_product_links (
                    id,
                    retailer_code,
                    receipt_text_normalized,
                    external_article_code,
                    global_product_id,
                    status,
                    confirmed_by
                ) VALUES (
                    'historical-incomplete',
                    'aldi',
                    'historisch incompleet',
                    '',
                    'product-no-gtin',
                    'confirmed',
                    'historical-contract-test'
                )
                """
            )
        )

        cleanup_count = (
            deactivate_incomplete_confirmed_external_links(conn)
        )
        _assert(
            cleanup_count == 1,
            "Historische opschoning raakte niet exact één koppeling",
        )

        historical_status = conn.execute(
            text(
                """
                SELECT status
                FROM external_article_product_links
                WHERE id = 'historical-incomplete'
                """
            )
        ).scalar_one()
        _assert(
            historical_status == "inactive",
            "Historische incomplete koppeling bleef actief",
        )

        complete_status = conn.execute(
            text(
                """
                SELECT status
                FROM external_article_product_links
                WHERE retailer_code = 'aldi'
                  AND external_article_code = '123456'
                """
            )
        ).scalar_one()
        _assert(
            complete_status == "confirmed",
            "Volledige koppeling is ten onrechte gedeactiveerd",
        )

        deactivated = deactivate_global_external_article_product_link(
            conn,
            retailer_code="ALDI",
            receipt_text="volledig artikel",
        )
        _assert(
            deactivated == 1,
            "Beëindigen raakte niet exact één actieve koppeling",
        )

        household_tables = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM sqlite_master
                WHERE type = 'table'
                  AND name IN (
                      'households',
                      'household_articles',
                      'inventory_events'
                  )
                """
            )
        ).scalar_one()
        _assert(
            household_tables == 0,
            "Contracttest heeft huishoud- of voorraadtabellen nodig",
        )

    print("PASS: volledige artikelen kunnen worden gekoppeld")
    print("PASS: GTIN/EAN is verplicht")
    print("PASS: passende GTIN-identiteit is verplicht")
    print("PASS: officieel GS1 GPC-Producttype is verplicht")
    print("PASS: inactieve universele artikelen worden geweigerd")
    print("PASS: historische incomplete koppelingen worden gedeactiveerd")
    print("PASS: volledige bestaande koppelingen blijven actief")
    print("PASS: vervanging bewaart historie")
    print("EXTERNAL_ARTICLE_PRODUCT_LINK_CONTRACT=GREEN")


if __name__ == "__main__":
    run_contract()
