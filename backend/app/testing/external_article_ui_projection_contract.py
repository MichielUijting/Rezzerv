"""Contracttest: alleen de centrale koppeling mag 'Gekoppeld' veroorzaken."""
from sqlalchemy import create_engine, text

from app.services.external_article_ui_projection import project_central_link_truth


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def run_contract():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE global_products (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO global_products VALUES
            ('product-a', '7 Granen Ontbijt', 'active'),
            ('product-b', 'Verkeerd Kandidaatproduct', 'active')
        """))
        conn.execute(text("""
            CREATE TABLE external_article_product_links (
                id TEXT PRIMARY KEY,
                retailer_code TEXT NOT NULL,
                receipt_text_normalized TEXT NOT NULL DEFAULT '',
                external_article_code TEXT NOT NULL DEFAULT '',
                global_product_id TEXT NOT NULL,
                status TEXT NOT NULL,
                confirmed_by TEXT,
                confirmed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                source_candidate_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))

        candidate_only = project_central_link_truth(conn, {
            "retailer_code": "aldi",
            "receipt_line_text": "7-GRANEN ONTBIJT",
            "status": "linked_to_catalog",
            "candidate_status": "linked_to_catalog",
            "global_product_id": "product-b",
            "is_linked_to_catalog": True,
            "candidates": [{"global_product_id": "product-b", "status": "linked_to_catalog"}],
        })
        assert_true(candidate_only["central_link_active"] is False, "Kandidaat werd centrale koppeling")
        assert_true(candidate_only["is_linked_to_catalog"] is False, "UI-status bleef ten onrechte gekoppeld")
        assert_true(candidate_only["status"] == "candidate", "Kandidaatstatus is niet teruggezet")
        assert_true(candidate_only["candidates"][0]["is_linked_to_catalog"] is False, "Geneste kandidaat bleef gekoppeld")

        conn.execute(text("""
            INSERT INTO external_article_product_links (
                id, retailer_code, receipt_text_normalized,
                external_article_code, global_product_id, status
            ) VALUES (
                'link-a', 'aldi', '7 granen ontbijt', '', 'product-a', 'confirmed'
            )
        """))

        central = project_central_link_truth(conn, {
            "retailer_code": "ALDI",
            "receipt_line_text": "7-GRANEN ONTBIJT",
            "status": "candidate",
            "candidates": [
                {"global_product_id": "product-a", "status": "candidate"},
                {"global_product_id": "product-b", "status": "linked_to_catalog"},
            ],
        })
        assert_true(central["central_link_active"] is True, "Centrale koppeling niet gevonden")
        assert_true(central["is_linked_to_catalog"] is True, "UI-status niet gekoppeld")
        assert_true(central["central_global_product_id"] == "product-a", "Verkeerd centraal product")
        assert_true(central["central_global_product_name"] == "7 Granen Ontbijt", "Productnaam ontbreekt")
        assert_true(central["candidates"][0]["is_linked_to_catalog"] is True, "Centrale kandidaat niet gemarkeerd")
        assert_true(central["candidates"][1]["is_linked_to_catalog"] is False, "Andere kandidaat ten onrechte gemarkeerd")

    print("PASS: kandidaatstatus alleen veroorzaakt geen Gekoppeld")
    print("PASS: alleen actieve centrale koppeling veroorzaakt Gekoppeld")
    print("PASS: centrale productnaam en product-id worden geprojecteerd")
    print("PASS: alleen de kandidaat van het centrale product is gekoppeld")


if __name__ == "__main__":
    run_contract()
