from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text

from app.db import engine


class GpcBrickAssignmentRequest(BaseModel):
    brick_code: str = Field(min_length=8, max_length=8)


def _ensure_schema() -> None:
    inspector = inspect(engine)
    required_tables = {
        "global_product_gpc_bricks",
        "gpc_translations",
    }
    missing_tables = sorted(required_tables - set(inspector.get_table_names()))
    if missing_tables:
        raise RuntimeError(
            "Canonical GPC assignment schema ontbreekt: "
            + ", ".join(missing_tables)
            + ". Voer Alembic migrations uit."
        )
    required_columns = {
        "global_product_id",
        "brick_code",
        "assignment_source",
        "confidence",
        "migrated_from",
        "updated_at",
    }
    actual_columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns("global_product_gpc_bricks")
    }
    missing_columns = sorted(required_columns - actual_columns)
    if missing_columns:
        raise RuntimeError(
            "Canonical GPC assignment schema wijkt af; ontbrekende kolommen: "
            + ", ".join(missing_columns)
        )


def _require_gpc_tables() -> None:
    tables = set(inspect(engine).get_table_names())
    required = {
        "global_products",
        "gpc_bricks",
        "gpc_classes",
        "gpc_families",
        "gpc_segments",
        "gpc_translations",
    }
    missing = sorted(required - tables)
    if missing:
        raise HTTPException(
            status_code=503,
            detail="De GS1 GPC-catalogus is nog niet volledig geïmporteerd.",
        )


def _require_read_context(main_module, authorization: Optional[str]) -> None:
    main_module.require_household_context(authorization)


def _require_write_context(main_module, authorization: Optional[str]) -> None:
    main_module.require_inventory_write_context(authorization, None)


def _global_product_exists(conn, global_product_id: str) -> bool:
    return bool(conn.execute(text("""
        SELECT 1
        FROM global_products
        WHERE id = :global_product_id
        LIMIT 1
    """), {"global_product_id": global_product_id}).first())


def _localized(column_alias: str, entity_type: str, code_column: str, source_column: str) -> str:
    return (
        "COALESCE((SELECT translated_text FROM gpc_translations tr "
        f"WHERE tr.entity_type='{entity_type}' AND tr.entity_code={column_alias}.{code_column} "
        "AND tr.language_code='nl'), "
        f"{column_alias}.{source_column})"
    )


def _brick_select_sql(where_clause: str) -> str:
    brick_label = _localized("b", "brick", "brick_code", "description")
    class_label = _localized("c", "class", "class_code", "description")
    family_label = _localized("f", "family", "family_code", "description")
    segment_label = _localized("s", "segment", "segment_code", "description")
    return f"""
        SELECT
            b.brick_code,
            {brick_label} AS brick_description,
            b.description AS brick_description_en,
            c.class_code,
            {class_label} AS class_description,
            f.family_code,
            {family_label} AS family_description,
            s.segment_code,
            {segment_label} AS segment_description
        FROM gpc_bricks b
        JOIN gpc_classes c ON c.class_code = b.class_code
        JOIN gpc_families f ON f.family_code = c.family_code
        JOIN gpc_segments s ON s.segment_code = f.segment_code
        {where_clause}
    """


def install_gpc_article_assignment_routes(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "gpc_article_assignment_routes_installed", False):
        return

    _ensure_schema()

    @app.get("/api/gpc/bricks")
    def search_gpc_bricks(
        query: str = Query(default="", max_length=200),
        limit: int = Query(default=25, ge=1, le=100),
        authorization: Optional[str] = Header(None),
    ):
        _require_read_context(main_module, authorization)
        _require_gpc_tables()
        normalized = " ".join(str(query or "").strip().split()).lower()
        params = {"query": f"%{normalized}%", "limit": limit}
        where = ""
        if normalized:
            where = """
                WHERE lower(b.brick_code) LIKE :query
                   OR lower(b.description) LIKE :query
                   OR lower(COALESCE((
                        SELECT translated_text FROM gpc_translations tr
                        WHERE tr.entity_type='brick'
                          AND tr.entity_code=b.brick_code
                          AND tr.language_code='nl'
                   ), '')) LIKE :query
            """
        sql = _brick_select_sql(where) + " ORDER BY brick_description, b.brick_code LIMIT :limit"
        with engine.begin() as conn:
            rows = [dict(row) for row in conn.execute(text(sql), params).mappings().all()]
        return {"items": rows, "total": len(rows), "query": normalized}

    @app.get("/api/catalog/{global_product_id}/gpc-brick")
    def get_catalog_product_gpc_brick(
        global_product_id: str,
        authorization: Optional[str] = Header(None),
    ):
        _require_read_context(main_module, authorization)
        _require_gpc_tables()
        _ensure_schema()
        with engine.begin() as conn:
            if not _global_product_exists(conn, global_product_id):
                raise HTTPException(status_code=404, detail="Universeel artikel niet gevonden")
            row = conn.execute(text(
                _brick_select_sql("""
                    JOIN global_product_gpc_bricks assignment
                      ON assignment.brick_code = b.brick_code
                    WHERE assignment.global_product_id = :global_product_id
                """)
            ), {"global_product_id": global_product_id}).mappings().first()
        return {"assignment": dict(row) if row else None}

    @app.put("/api/catalog/{global_product_id}/gpc-brick")
    def set_catalog_product_gpc_brick(
        global_product_id: str,
        payload: GpcBrickAssignmentRequest,
        authorization: Optional[str] = Header(None),
    ):
        _require_write_context(main_module, authorization)
        _require_gpc_tables()
        _ensure_schema()
        brick_code = str(payload.brick_code or "").strip()
        with engine.begin() as conn:
            if not _global_product_exists(conn, global_product_id):
                raise HTTPException(status_code=404, detail="Universeel artikel niet gevonden")
            if not conn.execute(
                text("SELECT 1 FROM gpc_bricks WHERE brick_code = :brick_code LIMIT 1"),
                {"brick_code": brick_code},
            ).first():
                raise HTTPException(status_code=400, detail="Onbekende GPC Brickcode")
            conn.execute(text("""
                INSERT INTO global_product_gpc_bricks (
                    global_product_id, brick_code, updated_at
                ) VALUES (:global_product_id, :brick_code, CURRENT_TIMESTAMP)
                ON CONFLICT(global_product_id) DO UPDATE SET
                    brick_code = excluded.brick_code,
                    updated_at = CURRENT_TIMESTAMP
            """), {"global_product_id": global_product_id, "brick_code": brick_code})
            row = conn.execute(text(
                _brick_select_sql("""
                    JOIN global_product_gpc_bricks assignment
                      ON assignment.brick_code = b.brick_code
                    WHERE assignment.global_product_id = :global_product_id
                """)
            ), {"global_product_id": global_product_id}).mappings().first()
        return {"status": "success", "assignment": dict(row)}

    @app.delete("/api/catalog/{global_product_id}/gpc-brick")
    def clear_catalog_product_gpc_brick(
        global_product_id: str,
        authorization: Optional[str] = Header(None),
    ):
        _require_write_context(main_module, authorization)
        _require_gpc_tables()
        _ensure_schema()
        with engine.begin() as conn:
            if not _global_product_exists(conn, global_product_id):
                raise HTTPException(status_code=404, detail="Universeel artikel niet gevonden")
            conn.execute(text(
                "DELETE FROM global_product_gpc_bricks WHERE global_product_id = :global_product_id"
            ), {"global_product_id": global_product_id})
        return {"status": "success", "assignment": None}

    app.state.gpc_article_assignment_routes_installed = True
