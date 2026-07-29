from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text

from app.db import engine


router = APIRouter(tags=["catalog-gpc"])


class GpcBrickAssignmentRequest(BaseModel):
    brick_code: str = Field(min_length=8, max_length=8)


def _tables() -> set[str]:
    return set(inspect(engine).get_table_names())


def _require_gpc_tables() -> None:
    required = {
        "global_products",
        "gpc_bricks",
        "gpc_classes",
        "gpc_families",
        "gpc_segments",
        "gpc_translations",
    }
    missing = sorted(required - _tables())
    if missing:
        raise HTTPException(
            status_code=503,
            detail="De GS1 GPC-catalogus is nog niet volledig geïmporteerd.",
        )


def _ensure_assignment_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS global_product_gpc_bricks (
                global_product_id TEXT PRIMARY KEY,
                brick_code VARCHAR(8) NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (global_product_id) REFERENCES global_products(id),
                FOREIGN KEY (brick_code) REFERENCES gpc_bricks(brick_code)
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_global_product_gpc_brick_code "
            "ON global_product_gpc_bricks(brick_code)"
        ))


def _global_product_exists(conn, global_product_id: str) -> bool:
    return bool(conn.execute(
        text("SELECT 1 FROM global_products WHERE id = :id LIMIT 1"),
        {"id": str(global_product_id)},
    ).first())


def _localized(alias: str, entity_type: str, code_column: str, source_column: str) -> str:
    return (
        "COALESCE((SELECT translated_text FROM gpc_translations tr "
        f"WHERE tr.entity_type='{entity_type}' "
        f"AND tr.entity_code={alias}.{code_column} "
        "AND tr.language_code='nl'), "
        f"{alias}.{source_column})"
    )


def _brick_select_sql(where_clause: str = "") -> str:
    return f"""
        SELECT
            b.brick_code,
            {_localized('b', 'brick', 'brick_code', 'description')} AS brick_description,
            b.description AS brick_description_en,
            c.class_code,
            {_localized('c', 'class', 'class_code', 'description')} AS class_description,
            f.family_code,
            {_localized('f', 'family', 'family_code', 'description')} AS family_description,
            s.segment_code,
            {_localized('s', 'segment', 'segment_code', 'description')} AS segment_description
        FROM gpc_bricks b
        JOIN gpc_classes c ON c.class_code = b.class_code
        JOIN gpc_families f ON f.family_code = c.family_code
        JOIN gpc_segments s ON s.segment_code = f.segment_code
        {where_clause}
    """


@router.get("/gpc/bricks")
def search_catalog_gpc_bricks(
    query: str = Query(default="", max_length=200),
    limit: int = Query(default=25, ge=1, le=100),
):
    _require_gpc_tables()
    normalized = " ".join(str(query or "").strip().split()).lower()
    where = ""
    params: dict[str, Any] = {"limit": int(limit)}
    if normalized:
        params["query"] = f"%{normalized}%"
        where = """
            WHERE lower(b.brick_code) LIKE :query
               OR lower(b.description) LIKE :query
               OR lower(COALESCE((
                    SELECT translated_text
                    FROM gpc_translations tr
                    WHERE tr.entity_type='brick'
                      AND tr.entity_code=b.brick_code
                      AND tr.language_code='nl'
               ), '')) LIKE :query
        """
    sql = _brick_select_sql(where) + " ORDER BY brick_description, b.brick_code LIMIT :limit"
    with engine.begin() as conn:
        rows = [dict(row) for row in conn.execute(text(sql), params).mappings().all()]
    return {"items": rows, "total": len(rows), "query": normalized}


@router.get("/{global_product_id}/gpc-brick")
def get_catalog_product_gpc_brick(global_product_id: str):
    _require_gpc_tables()
    _ensure_assignment_schema()
    with engine.begin() as conn:
        if not _global_product_exists(conn, global_product_id):
            raise HTTPException(status_code=404, detail="Universeel artikel niet gevonden")
        row = conn.execute(
            text(_brick_select_sql("""
                JOIN global_product_gpc_bricks assignment
                  ON assignment.brick_code = b.brick_code
                WHERE assignment.global_product_id = :global_product_id
            """)),
            {"global_product_id": global_product_id},
        ).mappings().first()
    return {"assignment": dict(row) if row else None}


@router.put("/{global_product_id}/gpc-brick")
def set_catalog_product_gpc_brick(
    global_product_id: str,
    payload: GpcBrickAssignmentRequest,
):
    _require_gpc_tables()
    _ensure_assignment_schema()
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
        """), {
            "global_product_id": global_product_id,
            "brick_code": brick_code,
        })
        row = conn.execute(
            text(_brick_select_sql("""
                JOIN global_product_gpc_bricks assignment
                  ON assignment.brick_code = b.brick_code
                WHERE assignment.global_product_id = :global_product_id
            """)),
            {"global_product_id": global_product_id},
        ).mappings().first()
    return {"status": "success", "assignment": dict(row)}


@router.delete("/{global_product_id}/gpc-brick")
def clear_catalog_product_gpc_brick(global_product_id: str):
    _require_gpc_tables()
    _ensure_assignment_schema()
    with engine.begin() as conn:
        if not _global_product_exists(conn, global_product_id):
            raise HTTPException(status_code=404, detail="Universeel artikel niet gevonden")
        conn.execute(
            text("DELETE FROM global_product_gpc_bricks WHERE global_product_id = :id"),
            {"id": global_product_id},
        )
    return {"status": "success", "assignment": None}
