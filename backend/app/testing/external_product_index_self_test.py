from __future__ import annotations

import os
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text

from app import external_product_index_api as index_api


def run_external_product_index_self_test() -> dict:
    fd, database_path = tempfile.mkstemp(prefix="rezzerv_external_product_index_", suffix=".db")
    os.close(fd)
    try:
        test_engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
        original_engine = index_api.engine
        index_api.engine = test_engine
        try:
            index_api.ensure_external_product_index_schema()
            with test_engine.begin() as conn:
                created = index_api.upsert_external_product_index_row(
                    conn,
                    index_api.ExternalProductIndexUpsertRequest(
                        source_name="open_food_facts",
                        source_product_code="8710398500345",
                        gtin="8710398500345",
                        product_name="Calvé Pindakaas",
                        brand="Calvé",
                        category="Broodbeleg",
                        quantity_label="350 g",
                        source_url="https://world.openfoodfacts.org/product/8710398500345",
                        raw_payload_json={"code": "8710398500345"},
                    ),
                )
                candidates = index_api.find_external_product_candidates(conn, query="pindakaas calve", limit=5)
                gtin_candidates = index_api.find_external_product_candidates(conn, gtin="8710398500345", limit=5)
                global_product_count = conn.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'global_products'")).scalar() or 0
                household_article_count = conn.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'household_articles'")).scalar() or 0
            assert created["source_name"] == "open_food_facts"
            assert created["gtin"] == "8710398500345"
            assert candidates, "Zoeken op tekst moet minimaal één externe kandidaat opleveren"
            assert candidates[0]["product_name"] == "Calvé Pindakaas"
            assert gtin_candidates and gtin_candidates[0]["gtin"] == "8710398500345"
            assert global_product_count == 0, "External index mag geen global_products-tabel aanmaken"
            assert household_article_count == 0, "External index mag geen Mijn artikel/household_articles-tabel aanmaken"
            return {
                "status": "passed",
                "created_id": created["id"],
                "candidate_count": len(candidates),
                "gtin_candidate_count": len(gtin_candidates),
                "creates_global_product": False,
                "creates_household_article": False,
            }
        finally:
            index_api.engine = original_engine
            test_engine.dispose()
    finally:
        try:
            Path(database_path).unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    print(run_external_product_index_self_test())
