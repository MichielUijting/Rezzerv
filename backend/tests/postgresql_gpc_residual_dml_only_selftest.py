from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api import catalog_gpc_routes
from app.services import gpc_article_assignment_service, gpc_import_service
from app.services.global_product_service import get_or_create_global_product
from app.services.gpc_translation_service import (
    ensure_gpc_translation_schema,
    import_gpc_translations_csv,
)

SEGMENT_CODE = "99000000"
FAMILY_CODE = "99010000"
CLASS_CODE = "99010100"
BRICK_CODE = "99010101"
TRANSLATION_SOURCE_NAME = "pr2l-gpc-translation.csv"


def _engine_url():
    raw_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        raise RuntimeError("DATABASE_URL is required")
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url


def _assert_runtime_create_denied(engine) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE pr2l_runtime_ddl_should_fail(id INTEGER)"))
    except ProgrammingError:
        print("POSTGRESQL_GPC_RESIDUAL_RUNTIME_CREATE_DENIED_GREEN")
        return
    raise AssertionError("Runtime role unexpectedly created a PR2l schema object")


def _assert_schema_validation_only(engine) -> None:
    before_tables = set(inspect(engine).get_table_names())
    catalog_gpc_routes._ensure_assignment_schema()
    gpc_article_assignment_service._ensure_schema()
    ensure_gpc_translation_schema(engine)
    with engine.begin() as conn:
        gpc_import_service._ensure_gpc_schema(conn)
    after_tables = set(inspect(engine).get_table_names())
    if before_tables != after_tables:
        raise AssertionError("GPC residual schema validation unexpectedly mutated runtime schema")
    required = {
        "global_product_gpc_bricks",
        "global_product_gpc_migration_suppressions",
        "gpc_translations",
        "gpc_translation_import_runs",
    }
    missing = required - after_tables
    if missing:
        raise AssertionError(f"Alembic head mist GPC residual tabellen: {sorted(missing)}")
    application_tables = after_tables - {"alembic_version"}
    print(
        "POSTGRESQL_GPC_RESIDUAL_SCHEMA_VALIDATION_ONLY_GREEN "
        f"application_tables={len(application_tables)}"
    )


def _seed_reference_data(conn) -> None:
    conn.execute(text("""
        INSERT INTO gpc_segments (segment_code, description)
        VALUES (:code, 'PR2l Segment')
        ON CONFLICT(segment_code) DO UPDATE SET description = excluded.description
    """), {"code": SEGMENT_CODE})
    conn.execute(text("""
        INSERT INTO gpc_families (family_code, description, segment_code)
        VALUES (:code, 'PR2l Family', :segment_code)
        ON CONFLICT(family_code) DO UPDATE SET
            description = excluded.description,
            segment_code = excluded.segment_code
    """), {"code": FAMILY_CODE, "segment_code": SEGMENT_CODE})
    conn.execute(text("""
        INSERT INTO gpc_classes (class_code, description, family_code)
        VALUES (:code, 'PR2l Class', :family_code)
        ON CONFLICT(class_code) DO UPDATE SET
            description = excluded.description,
            family_code = excluded.family_code
    """), {"code": CLASS_CODE, "family_code": FAMILY_CODE})
    conn.execute(text("""
        INSERT INTO gpc_bricks (brick_code, description, class_code)
        VALUES (:code, 'PR2l Brick', :class_code)
        ON CONFLICT(brick_code) DO UPDATE SET
            description = excluded.description,
            class_code = excluded.class_code
    """), {"code": BRICK_CODE, "class_code": CLASS_CODE})


def _cleanup(conn, product_id: str | None = None) -> None:
    if product_id:
        conn.execute(
            text("DELETE FROM global_product_gpc_bricks WHERE global_product_id = :id"),
            {"id": product_id},
        )
        conn.execute(
            text("DELETE FROM global_product_gpc_migration_suppressions WHERE global_product_id = :id"),
            {"id": product_id},
        )
        conn.execute(text("DELETE FROM global_products WHERE id = :id"), {"id": product_id})
    conn.execute(
        text("DELETE FROM gpc_translation_import_runs WHERE source_name = :source_name"),
        {"source_name": TRANSLATION_SOURCE_NAME},
    )
    conn.execute(text("""
        DELETE FROM gpc_translations
        WHERE entity_type = 'brick' AND entity_code = :brick_code AND language_code = 'nl'
    """), {"brick_code": BRICK_CODE})
    conn.execute(
        text("DELETE FROM product_inventory_groups WHERE inventory_group_key = :key"),
        {"key": f"gpc:{BRICK_CODE}"},
    )
    conn.execute(
        text("DELETE FROM gpc_product_groups WHERE gpc_brick_code = :brick_code"),
        {"brick_code": BRICK_CODE},
    )
    conn.execute(text("DELETE FROM gpc_bricks WHERE brick_code = :code"), {"code": BRICK_CODE})
    conn.execute(text("DELETE FROM gpc_classes WHERE class_code = :code"), {"code": CLASS_CODE})
    conn.execute(text("DELETE FROM gpc_families WHERE family_code = :code"), {"code": FAMILY_CODE})
    conn.execute(text("DELETE FROM gpc_segments WHERE segment_code = :code"), {"code": SEGMENT_CODE})


def _assert_assignment_dml(engine) -> str:
    with engine.begin() as conn:
        _cleanup(conn)
        _seed_reference_data(conn)
        product_id = get_or_create_global_product(
            conn,
            gtin="9901010199010",
            name="PR2l GPC product",
            source="postgresql_pr2l_selftest",
        )

    payload = catalog_gpc_routes.GpcBrickAssignmentRequest(brick_code=BRICK_CODE)
    written = catalog_gpc_routes.set_catalog_product_gpc_brick(product_id, payload)
    assignment = written.get("assignment") or {}
    if assignment.get("brick_code") != BRICK_CODE:
        raise AssertionError(written)
    read = catalog_gpc_routes.get_catalog_product_gpc_brick(product_id)
    if (read.get("assignment") or {}).get("brick_code") != BRICK_CODE:
        raise AssertionError(read)
    cleared = catalog_gpc_routes.clear_catalog_product_gpc_brick(product_id)
    if cleared.get("assignment") is not None:
        raise AssertionError(cleared)
    with engine.begin() as conn:
        suppressed = conn.execute(text("""
            SELECT 1 FROM global_product_gpc_migration_suppressions
            WHERE global_product_id = :id
        """), {"id": product_id}).scalar()
        if not suppressed:
            raise AssertionError("GPC migration suppression was not persisted")
    print("POSTGRESQL_GPC_ASSIGNMENT_DML_ONLY_GREEN")
    return product_id


def _assert_translation_dml(engine) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = Path(temp_dir) / TRANSLATION_SOURCE_NAME
        csv_path.write_text(
            "entity_type,entity_code,language_code,translated_text,translation_source,reviewed\n"
            f"brick,{BRICK_CODE},nl,PR2l Baksteen,selftest,1\n",
            encoding="utf-8",
        )
        result = import_gpc_translations_csv(
            csv_path,
            required_language="nl",
            require_complete=False,
            db_engine=engine,
        )
    if int((result.get("counts") or {}).get("inserted") or 0) != 1:
        raise AssertionError(result)
    with engine.begin() as conn:
        translated = conn.execute(text("""
            SELECT translated_text FROM gpc_translations
            WHERE entity_type='brick' AND entity_code=:brick_code AND language_code='nl'
        """), {"brick_code": BRICK_CODE}).scalar_one_or_none()
    if translated != "PR2l Baksteen":
        raise AssertionError(translated)
    print("POSTGRESQL_GPC_TRANSLATION_DML_ONLY_GREEN")


def _assert_import_projection_dml(engine) -> None:
    row = {
        "gpc_segment_code": SEGMENT_CODE,
        "gpc_segment_name": "PR2l Segment",
        "gpc_family_code": FAMILY_CODE,
        "gpc_family_name": "PR2l Family",
        "gpc_class_code": CLASS_CODE,
        "gpc_class_name": "PR2l Class",
        "gpc_brick_code": BRICK_CODE,
        "gpc_brick_name": "PR2l Brick",
    }
    timestamp = gpc_import_service.now_iso()
    with engine.begin() as conn:
        action = gpc_import_service._upsert_gpc_row(conn, row, "nl", "pr2l", timestamp)
        if action not in {"created", "updated"}:
            raise AssertionError(action)
        projection_action = gpc_import_service._upsert_rezzerv_product_group(conn, row, timestamp)
        if projection_action not in {"created", "updated"}:
            raise AssertionError(projection_action)
        active = conn.execute(text("""
            SELECT active FROM gpc_product_groups WHERE gpc_brick_code = :brick_code
        """), {"brick_code": BRICK_CODE}).scalar_one()
        if active is not True:
            raise AssertionError(f"Expected PostgreSQL BOOLEAN TRUE, got {active!r}")
    print("POSTGRESQL_GPC_IMPORT_BOOLEAN_DML_ONLY_GREEN")


def main() -> None:
    engine = create_engine(_engine_url(), future=True)
    product_id: str | None = None
    try:
        _assert_runtime_create_denied(engine)
        _assert_schema_validation_only(engine)
        product_id = _assert_assignment_dml(engine)
        _assert_translation_dml(engine)
        _assert_import_projection_dml(engine)
        with engine.begin() as conn:
            _cleanup(conn, product_id)
    finally:
        engine.dispose()
    print("POSTGRESQL_GPC_RESIDUAL_DML_ONLY_GREEN")
    print("POSTGRESQL_GPC_RESIDUAL_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
