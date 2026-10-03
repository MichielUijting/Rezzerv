import json
from pathlib import Path

from sqlalchemy import create_engine, text

from app.services.dutch_gpc_projection_service import (
    BUNDLED_DUTCH_GPC_PATH,
    ensure_bundled_dutch_gpc_reference,
)


def test_bundled_dutch_gpc_reference_is_complete_and_contains_product_families():
    payload = json.loads(Path(BUNDLED_DUTCH_GPC_PATH).read_text(encoding="utf-8"))
    rows = list(payload.get("bricks") or [])

    assert payload["source"] == "GS1 GPC Browser"
    assert payload["language_code"] == "nl"
    assert payload["publication_version"] == "v20260520"
    assert payload["brick_count"] == 5318
    assert len(rows) == 5318
    assert len({row["gpc_brick_code"] for row in rows}) == 5318

    required = {
        "gpc_brick_code",
        "gpc_brick_name",
        "gpc_class_code",
        "gpc_class_name",
        "gpc_family_code",
        "gpc_family_name",
        "gpc_segment_code",
        "gpc_segment_name",
    }
    assert all(required.issubset(row) for row in rows)
    assert all(str(row["gpc_brick_name"]).strip() for row in rows)
    assert all(str(row["gpc_family_name"]).strip() for row in rows)

    banana = next(row for row in rows if row["gpc_brick_code"] == "10005897")
    assert banana["gpc_brick_name"] == "Bananen (Cavendish)"
    assert banana["gpc_class_name"] == "Bananen"
    assert banana["gpc_family_code"] == "50250000"
    assert banana["gpc_family_name"] == "Fruit - Onbewerkt/Onverwerkt (Vers)"


def test_bundled_dutch_gpc_reference_can_seed_empty_runtime_table():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE gpc_product_groups (
                    gpc_brick_code TEXT PRIMARY KEY,
                    gpc_brick_name TEXT,
                    gpc_class_code TEXT,
                    gpc_class_name TEXT,
                    gpc_family_code TEXT,
                    gpc_family_name TEXT,
                    gpc_segment_code TEXT,
                    gpc_segment_name TEXT,
                    language_code TEXT,
                    source_version TEXT,
                    active INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )
            """))

            result = ensure_bundled_dutch_gpc_reference(conn)

            assert result["expected"] == 5318
            assert result["loaded"] == 5318
            assert result["source_version"] == "v20260520"

            count = conn.execute(text("""
                SELECT COUNT(*)
                FROM gpc_product_groups
                WHERE language_code = 'nl'
                  AND trim(COALESCE(gpc_family_name, '')) <> ''
            """)).scalar_one()
            assert count == 5318

            banana = conn.execute(text("""
                SELECT gpc_brick_name, gpc_family_name
                FROM gpc_product_groups
                WHERE gpc_brick_code = '10005897'
            """)).mappings().one()
            assert banana["gpc_brick_name"] == "Bananen (Cavendish)"
            assert banana["gpc_family_name"] == "Fruit - Onbewerkt/Onverwerkt (Vers)"
    finally:
        engine.dispose()
