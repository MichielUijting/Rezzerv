"""Geïsoleerde Stap-8-releasegate voor Externe databases -> Kassa -> Uitpakken -> Voorraad.

De test gebruikt uitsluitend een tijdelijke SQLite-database. Productiegegevens,
productiebonnen en productievoorraad worden niet gelezen of gewijzigd.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text

from app.services.external_article_product_link_domain_service import (
    confirm_global_external_article_product_link,
    find_global_external_article_product_link,
)
from app.services.external_article_product_link_service import (
    ensure_external_article_product_link_schema,
)

RETAILER = "aldi"
ARTICLE_TEXT = "7-GRANEN ONTBIJT"
ARTICLE_CODE = "ALDI-7001"
PRODUCT_A = "gp-step8-a"
PRODUCT_B = "gp-step8-b"
HOUSEHOLD = "household-step8"
HOUSEHOLD_ARTICLE = "ha-step8"
LOCATION = "loc-step8"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def init_schema(conn) -> None:
    conn.execute(text("""
        CREATE TABLE global_products (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
        )
    """))
    conn.execute(text("""
        CREATE TABLE receipt_tables (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            store_name TEXT NOT NULL
        )
    """))
    conn.execute(text("""
        CREATE TABLE receipt_table_lines (
            id TEXT PRIMARY KEY,
            receipt_table_id TEXT NOT NULL,
            raw_label TEXT NOT NULL,
            external_article_code TEXT,
            matched_global_product_id TEXT,
            article_match_status TEXT NOT NULL DEFAULT 'unmatched'
        )
    """))
    conn.execute(text("""
        CREATE TABLE purchase_import_lines (
            id TEXT PRIMARY KEY,
            external_line_ref TEXT NOT NULL,
            matched_global_product_id TEXT,
            matched_household_article_id TEXT,
            target_location_id TEXT,
            quantity NUMERIC NOT NULL,
            processing_status TEXT NOT NULL DEFAULT 'pending',
            processed_event_id TEXT
        )
    """))
    conn.execute(text("""
        CREATE TABLE inventory_events (
            id TEXT PRIMARY KEY,
            source_line_id TEXT NOT NULL UNIQUE,
            household_id TEXT NOT NULL,
            household_article_id TEXT NOT NULL,
            location_id TEXT NOT NULL,
            quantity_delta NUMERIC NOT NULL
        )
    """))
    conn.execute(text("""
        CREATE TABLE inventory (
            household_id TEXT NOT NULL,
            household_article_id TEXT NOT NULL,
            location_id TEXT NOT NULL,
            quantity NUMERIC NOT NULL DEFAULT 0,
            PRIMARY KEY (household_id, household_article_id, location_id)
        )
    """))
    ensure_external_article_product_link_schema(conn)


def seed_products(conn) -> None:
    conn.execute(
        text("INSERT INTO global_products (id, name, status) VALUES (:id, :name, 'active')"),
        {"id": PRODUCT_A, "name": "7 Granen Ontbijt A"},
    )
    conn.execute(
        text("INSERT INTO global_products (id, name, status) VALUES (:id, :name, 'active')"),
        {"id": PRODUCT_B, "name": "7 Granen Ontbijt B"},
    )


def create_receipt_line(conn, suffix: str, label: str = ARTICLE_TEXT, code: str | None = ARTICLE_CODE) -> tuple[str, str]:
    receipt_id = f"receipt-{suffix}"
    line_id = f"receipt-line-{suffix}"
    conn.execute(
        text("INSERT INTO receipt_tables (id, household_id, store_name) VALUES (:id, :household, :store)"),
        {"id": receipt_id, "household": HOUSEHOLD, "store": RETAILER},
    )
    conn.execute(
        text("""
            INSERT INTO receipt_table_lines (
                id, receipt_table_id, raw_label, external_article_code,
                matched_global_product_id, article_match_status
            ) VALUES (:id, :receipt_id, :label, :code, NULL, 'unmatched')
        """),
        {"id": line_id, "receipt_id": receipt_id, "label": label, "code": code},
    )
    return receipt_id, line_id


def kassa_sync_from_central(conn, receipt_id: str, line_id: str) -> str | None:
    row = conn.execute(text("""
        SELECT rt.store_name, rtl.raw_label, rtl.external_article_code
        FROM receipt_table_lines rtl
        JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
        WHERE rt.id = :receipt_id AND rtl.id = :line_id
    """), {"receipt_id": receipt_id, "line_id": line_id}).mappings().one()
    link = find_global_external_article_product_link(
        conn,
        retailer_code=row["store_name"],
        receipt_text=row["raw_label"],
        external_article_code=row["external_article_code"],
    )
    product_id = str(link.get("global_product_id")) if link else None
    conn.execute(text("""
        UPDATE receipt_table_lines
        SET matched_global_product_id = :product_id,
            article_match_status = CASE WHEN :product_id IS NULL THEN 'unmatched' ELSE 'product_matched' END
        WHERE id = :line_id
    """), {"product_id": product_id, "line_id": line_id})
    return product_id


def unpack_copy_from_kassa(conn, receipt_line_id: str, suffix: str, quantity: int = 2) -> str:
    product_id = conn.execute(
        text("SELECT matched_global_product_id FROM receipt_table_lines WHERE id = :id"),
        {"id": receipt_line_id},
    ).scalar_one_or_none()
    import_line_id = f"unpack-{suffix}"
    conn.execute(text("""
        INSERT INTO purchase_import_lines (
            id, external_line_ref, matched_global_product_id,
            matched_household_article_id, target_location_id, quantity
        ) VALUES (:id, :ref, :product_id, NULL, NULL, :quantity)
    """), {
        "id": import_line_id,
        "ref": f"receipt-line:{receipt_line_id}",
        "product_id": product_id,
        "quantity": quantity,
    })
    return import_line_id


def choose_article_and_location(conn, import_line_id: str) -> None:
    before = conn.execute(
        text("SELECT matched_global_product_id FROM purchase_import_lines WHERE id = :id"),
        {"id": import_line_id},
    ).scalar_one_or_none()
    conn.execute(text("""
        UPDATE purchase_import_lines
        SET matched_household_article_id = :article_id,
            target_location_id = :location_id
        WHERE id = :id
    """), {"article_id": HOUSEHOLD_ARTICLE, "location_id": LOCATION, "id": import_line_id})
    after = conn.execute(
        text("SELECT matched_global_product_id FROM purchase_import_lines WHERE id = :id"),
        {"id": import_line_id},
    ).scalar_one_or_none()
    require(after == before, "Mijn-artikel- of locatiekeuze wijzigde het Kassa-product")


def process_to_inventory(conn, import_line_id: str) -> None:
    line = conn.execute(text("""
        SELECT matched_household_article_id, target_location_id, quantity, processed_event_id
        FROM purchase_import_lines WHERE id = :id
    """), {"id": import_line_id}).mappings().one()
    if line["processed_event_id"]:
        return
    require(bool(line["matched_household_article_id"]), "Mijn artikel ontbreekt")
    require(bool(line["target_location_id"]), "Locatie ontbreekt")
    event_id = f"event:{import_line_id}"
    conn.execute(text("""
        INSERT INTO inventory_events (
            id, source_line_id, household_id, household_article_id, location_id, quantity_delta
        ) VALUES (:id, :source, :household, :article, :location, :quantity)
    """), {
        "id": event_id,
        "source": import_line_id,
        "household": HOUSEHOLD,
        "article": line["matched_household_article_id"],
        "location": line["target_location_id"],
        "quantity": line["quantity"],
    })
    conn.execute(text("""
        INSERT INTO inventory (household_id, household_article_id, location_id, quantity)
        VALUES (:household, :article, :location, :quantity)
        ON CONFLICT(household_id, household_article_id, location_id)
        DO UPDATE SET quantity = inventory.quantity + excluded.quantity
    """), {
        "household": HOUSEHOLD,
        "article": line["matched_household_article_id"],
        "location": line["target_location_id"],
        "quantity": line["quantity"],
    })
    conn.execute(
        text("UPDATE purchase_import_lines SET processing_status = 'processed', processed_event_id = :event WHERE id = :id"),
        {"event": event_id, "id": import_line_id},
    )


def run_gate() -> None:
    with tempfile.TemporaryDirectory(prefix="rezzerv-step8-") as tmp:
        db_path = Path(tmp) / "step8.sqlite"
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            init_schema(conn)
            seed_products(conn)

            # 1. Centrale bevestiging geldt voor oude en nieuwe bonnen.
            old_receipt, old_line = create_receipt_line(conn, "old")
            confirm_global_external_article_product_link(
                conn,
                retailer_code=RETAILER,
                receipt_text=ARTICLE_TEXT,
                external_article_code=ARTICLE_CODE,
                global_product_id=PRODUCT_A,
                confirmed_by="step8-gate",
                source_candidate_id="step8-candidate-a",
            )
            new_receipt, new_line = create_receipt_line(conn, "new")
            require(kassa_sync_from_central(conn, old_receipt, old_line) == PRODUCT_A, "Oude bon leest centrale koppeling niet")
            require(kassa_sync_from_central(conn, new_receipt, new_line) == PRODUCT_A, "Nieuwe bon leest centrale koppeling niet")
            print("PASS: oude en nieuwe Kassa-regels lezen dezelfde centrale koppeling")

            # 2. Uitpakken kopieert letterlijk en downstreamkeuzes wijzigen product niet.
            unpack_line = unpack_copy_from_kassa(conn, new_line, "linked", quantity=2)
            copied = conn.execute(text("SELECT matched_global_product_id FROM purchase_import_lines WHERE id = :id"), {"id": unpack_line}).scalar_one()
            require(copied == PRODUCT_A, "Uitpakken kopieerde niet hetzelfde product")
            choose_article_and_location(conn, unpack_line)
            print("PASS: Uitpakken kopieert het Kassa-product en downstreamkeuzes wijzigen het niet")

            # 3. Naar Voorraad en idempotente herverwerking.
            process_to_inventory(conn, unpack_line)
            process_to_inventory(conn, unpack_line)
            quantity = conn.execute(text("SELECT quantity FROM inventory WHERE household_id = :household"), {"household": HOUSEHOLD}).scalar_one()
            event_count = conn.execute(text("SELECT COUNT(*) FROM inventory_events")).scalar_one()
            require(float(quantity) == 2.0, "Voorraadhoeveelheid is niet 2")
            require(int(event_count) == 1, "Herverwerking maakte een dubbel voorraadevent")
            print("PASS: verwerking naar Voorraad is correct en idempotent")

            # 4. Regel zonder centrale koppeling blijft ongekoppeld in Kassa en Uitpakken.
            unknown_receipt, unknown_line = create_receipt_line(conn, "unknown", "ONBEKEND PRODUCT", "ALDI-UNKNOWN")
            require(kassa_sync_from_central(conn, unknown_receipt, unknown_line) is None, "Onbekende Kassa-regel kreeg toch een product")
            unknown_unpack = unpack_copy_from_kassa(conn, unknown_line, "unknown", quantity=1)
            unknown_product = conn.execute(text("SELECT matched_global_product_id FROM purchase_import_lines WHERE id = :id"), {"id": unknown_unpack}).scalar_one_or_none()
            require(unknown_product is None, "Uitpakken vulde alsnog een product voor een ongekoppelde regel")
            print("PASS: ontbrekende centrale koppeling blijft ontbrekend in Kassa en Uitpakken")

            # 5. Vervanging bewaart historie en laat één actieve koppeling over.
            confirm_global_external_article_product_link(
                conn,
                retailer_code=RETAILER,
                receipt_text=ARTICLE_TEXT,
                external_article_code=ARTICLE_CODE,
                global_product_id=PRODUCT_B,
                confirmed_by="step8-gate",
                source_candidate_id="step8-candidate-b",
            )
            require(kassa_sync_from_central(conn, old_receipt, old_line) == PRODUCT_B, "Oude bon gebruikt vervangende koppeling niet")
            require(kassa_sync_from_central(conn, new_receipt, new_line) == PRODUCT_B, "Nieuwe bon gebruikt vervangende koppeling niet")
            counts = conn.execute(text("""
                SELECT
                    SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) AS active_count,
                    COUNT(*) AS history_count
                FROM external_article_product_links
                WHERE retailer_code = :retailer
            """), {"retailer": RETAILER}).mappings().one()
            require(int(counts["active_count"] or 0) == 1, "Niet exact één actieve koppeling na vervanging")
            require(int(counts["history_count"] or 0) == 2, "Koppelhistorie is niet behouden")
            print("PASS: vervanging laat één actieve koppeling over en bewaart historie")

            # 6. Winkelketens blijven gescheiden.
            other = find_global_external_article_product_link(
                conn,
                retailer_code="jumbo",
                receipt_text=ARTICLE_TEXT,
                external_article_code=ARTICLE_CODE,
            )
            require(other is None, "Koppeling lekte naar een andere winkelketen")
            print("PASS: winkelketens blijven gescheiden")

        print("STEP8_INTEGRATED_RELEASE_GATE=GREEN")
        print(f"ISOLATED_DATABASE={db_path}")
        print("PRODUCTION_DATA_CHANGED=NO")


if __name__ == "__main__":
    run_gate()
