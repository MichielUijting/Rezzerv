"""Geïsoleerde contracttest voor algemene winkelartikelkoppelingen.

Draait op een tijdelijke SQLite-database en raakt geen normale runtime-data.
Uitvoeren vanuit de backendcontainer:

    python -m app.testing.external_article_product_link_contract
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.external_article_product_link_domain_service import (
    confirm_global_external_article_product_link,
    deactivate_global_external_article_product_link,
    find_global_external_article_product_link,
)


def _create_test_database():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE global_products (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO global_products (id, name, status) VALUES
                    ('product-a', '7 Granen Ontbijt', 'active'),
                    ('product-b', 'Ander Ontbijt', 'active'),
                    ('product-inactive', 'Inactief Product', 'inactive')
                """
            )
        )
    return engine


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_contract() -> None:
    engine = _create_test_database()

    with engine.begin() as conn:
        first = confirm_global_external_article_product_link(
            conn,
            retailer_code="ALDI",
            receipt_text="7-GRANEN ONTBIJT",
            global_product_id="product-a",
            confirmed_by="contract-test",
        )
        _assert(first["retailer_code"] == "aldi", "Winkelcode is niet canoniek opgeslagen")
        _assert(
            first["receipt_text_normalized"] == "7 granen ontbijt",
            "Bontekst is niet canoniek opgeslagen",
        )

        found = find_global_external_article_product_link(
            conn,
            retailer_code="Aldi",
            receipt_text="7 granen ontbijt",
        )
        _assert(found is not None, "Algemene koppeling is niet teruggevonden")
        _assert(found["global_product_id"] == "product-a", "Verkeerd universeel artikel gevonden")

        other_retailer = find_global_external_article_product_link(
            conn,
            retailer_code="LIDL",
            receipt_text="7-GRANEN ONTBIJT",
        )
        _assert(other_retailer is None, "Koppeling lekt naar een andere winkelketen")

        replacement = confirm_global_external_article_product_link(
            conn,
            retailer_code="aldi",
            receipt_text="7 granen ontbijt",
            global_product_id="product-b",
            confirmed_by="contract-test-correction",
        )
        _assert(replacement["global_product_id"] == "product-b", "Vervanging is niet opgeslagen")

        active_count = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM external_article_product_links
                WHERE retailer_code = 'aldi'
                  AND receipt_text_normalized = '7 granen ontbijt'
                  AND status = 'confirmed'
                """
            )
        ).scalar_one()
        inactive_count = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM external_article_product_links
                WHERE retailer_code = 'aldi'
                  AND receipt_text_normalized = '7 granen ontbijt'
                  AND status = 'inactive'
                """
            )
        ).scalar_one()
        _assert(active_count == 1, "Er is niet precies één actieve koppeling")
        _assert(inactive_count == 1, "De vervangen koppeling is niet als historie bewaard")

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
        _assert(by_code is not None, "Koppeling op winkelartikelcode is niet gevonden")
        _assert(by_code["global_product_id"] == "product-a", "Artikelcode vond verkeerd product")

        deactivated = deactivate_global_external_article_product_link(
            conn,
            retailer_code="ALDI",
            receipt_text="7-GRANEN ONTBIJT",
        )
        _assert(deactivated == 1, "Beëindigen heeft niet exact één actieve koppeling geraakt")
        after_deactivate = find_global_external_article_product_link(
            conn,
            retailer_code="aldi",
            receipt_text="7 granen ontbijt",
        )
        _assert(after_deactivate is None, "Beëindigde koppeling wordt nog teruggegeven")

        try:
            confirm_global_external_article_product_link(
                conn,
                retailer_code="ALDI",
                receipt_text="Inactief",
                global_product_id="product-inactive",
            )
        except ValueError as exc:
            _assert("niet actief" in str(exc), "Verkeerde fout bij inactief universeel artikel")
        else:
            raise AssertionError("Inactief universeel artikel kon toch worden gekoppeld")

        household_tables = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM sqlite_master
                WHERE type = 'table'
                  AND name IN ('households', 'household_articles', 'inventory_events')
                """
            )
        ).scalar_one()
        _assert(household_tables == 0, "Contracttest heeft huishoud- of voorraadtabellen nodig")

    print("PASS: algemene koppeling geldt zonder bon- of huishouden-ID")
    print("PASS: winkelketens blijven gescheiden")
    print("PASS: vervanging bewaart historie en laat één actieve koppeling over")
    print("PASS: winkelartikelcode heeft voorrang bij opvragen")
    print("PASS: beëindigen verwijdert niets fysiek")
    print("PASS: inactieve universele artikelen worden geweigerd")
    print("PASS: geen household- of voorraadtabellen gebruikt")


if __name__ == "__main__":
    run_contract()
