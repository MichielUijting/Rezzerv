from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.global_product_service import build_global_product_fingerprint, get_or_create_global_product


def run() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE global_products (
                id TEXT PRIMARY KEY,
                primary_gtin TEXT,
                name TEXT NOT NULL,
                brand TEXT,
                variant TEXT,
                category TEXT,
                size_value NUMERIC,
                size_unit TEXT,
                product_fingerprint TEXT,
                source TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX idx_global_products_primary_gtin
            ON global_products(primary_gtin)
            WHERE primary_gtin IS NOT NULL AND trim(primary_gtin) <> ''
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX uq_global_products_active_fingerprint
            ON global_products(product_fingerprint)
            WHERE status = 'active'
              AND COALESCE(trim(primary_gtin), '') = ''
              AND COALESCE(trim(product_fingerprint), '') <> ''
        """))

        pizza_ids = {get_or_create_global_product(conn, gtin=None, name=value, source="test") for value in ("Pizza", " pizza ", "PIZZA")}
        assert len(pizza_ids) == 1, pizza_ids

        rice_plain = get_or_create_global_product(conn, gtin=None, name="Rijstwafel", variant=None, source="test")
        rice_chocolate = get_or_create_global_product(conn, gtin=None, name="Rijstwafel", variant="Chocolade", source="test")
        assert rice_plain != rice_chocolate

        gtin_one = get_or_create_global_product(conn, gtin="8712345678901", name="Vruchtendrank", source="test")
        gtin_two = get_or_create_global_product(conn, gtin="8712345678901", name="Vruchtendrank vernieuwd", source="test")
        assert gtin_one == gtin_two

        total = conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one()
        assert total == 4, total

        pizza_fingerprint = build_global_product_fingerprint("Pizza")
        pizza_count = conn.execute(text("SELECT COUNT(*) FROM global_products WHERE product_fingerprint=:fp"), {"fp": pizza_fingerprint}).scalar_one()
        assert pizza_count == 1, pizza_count

    print("PASS: generieke catalogusproducten worden centraal hergebruikt")
    print("PASS: relevante varianten blijven afzonderlijke producten")
    print("PASS: gelijke GTIN wordt hergebruikt")
    print("PASS: unieke fingerprint-index blokkeert inhoudelijke doublures")


if __name__ == "__main__":
    run()
