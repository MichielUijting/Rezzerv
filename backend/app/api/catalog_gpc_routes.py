from __future__ import annotations

import re
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


def _columns(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {str(column.get("name") or "") for column in inspect(engine).get_columns(table_name)}


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
                assignment_source TEXT NOT NULL DEFAULT 'manual_catalog_detail',
                confidence REAL NOT NULL DEFAULT 1.0,
                migrated_from TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (global_product_id) REFERENCES global_products(id),
                FOREIGN KEY (brick_code) REFERENCES gpc_bricks(brick_code)
            )
        """))
        existing_columns = {
            str(row[1])
            for row in conn.execute(text("PRAGMA table_info(global_product_gpc_bricks)")).fetchall()
        }
        for column, definition in (
            ("assignment_source", "TEXT NOT NULL DEFAULT 'manual_catalog_detail'"),
            ("confidence", "REAL NOT NULL DEFAULT 1.0"),
            ("migrated_from", "TEXT"),
        ):
            if column not in existing_columns:
                conn.execute(text(
                    f"ALTER TABLE global_product_gpc_bricks ADD COLUMN {column} {definition}"
                ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_global_product_gpc_brick_code "
            "ON global_product_gpc_bricks(brick_code)"
        ))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS global_product_gpc_migration_suppressions (
                global_product_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (global_product_id) REFERENCES global_products(id)
            )
        """))


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


def _brick_select_sql(where_clause: str = "", assignment_alias: str | None = None) -> str:
    assignment_fields = ""
    if assignment_alias:
        assignment_fields = f""",
            {assignment_alias}.assignment_source,
            {assignment_alias}.confidence,
            {assignment_alias}.migrated_from,
            {assignment_alias}.updated_at AS assignment_updated_at
        """
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
            {assignment_fields}
        FROM gpc_bricks b
        JOIN gpc_classes c ON c.class_code = b.class_code
        JOIN gpc_families f ON f.family_code = c.family_code
        JOIN gpc_segments s ON s.segment_code = f.segment_code
        {where_clause}
    """


def _assignment_row(conn, global_product_id: str):
    return conn.execute(
        text(_brick_select_sql("""
            JOIN global_product_gpc_bricks assignment
              ON assignment.brick_code = b.brick_code
            WHERE assignment.global_product_id = :global_product_id
        """, assignment_alias="assignment")),
        {"global_product_id": global_product_id},
    ).mappings().first()


def _legacy_candidate(conn, global_product_id: str) -> dict[str, Any] | None:
    tables = _tables()
    if not {"product_group_memberships", "product_inventory_groups"}.issubset(tables):
        return None
    required_membership = {"global_product_id", "inventory_group_key"}
    required_group = {"inventory_group_key", "gpc_brick_code"}
    if not required_membership.issubset(_columns("product_group_memberships")):
        return None
    if not required_group.issubset(_columns("product_inventory_groups")):
        return None

    membership_columns = _columns("product_group_memberships")
    confidence_sql = "COALESCE(pgm.confidence, 1.0)" if "confidence" in membership_columns else "1.0"
    confirmed_sql = "COALESCE(pgm.confirmed_by_user, 0)" if "confirmed_by_user" in membership_columns else "0"
    active_sql = "COALESCE(pgm.active, 1)" if "active" in membership_columns else "1"
    source_sql = "COALESCE(pgm.source, 'product_group_membership')" if "source" in membership_columns else "'product_group_membership'"

    row = conn.execute(text(f"""
        SELECT
            pig.gpc_brick_code AS brick_code,
            {confidence_sql} AS confidence,
            {confirmed_sql} AS confirmed_by_user,
            {source_sql} AS legacy_source,
            pgm.inventory_group_key
        FROM product_group_memberships pgm
        JOIN product_inventory_groups pig
          ON pig.inventory_group_key = pgm.inventory_group_key
        JOIN gpc_bricks b
          ON b.brick_code = pig.gpc_brick_code
        WHERE pgm.global_product_id = :global_product_id
          AND {active_sql} = 1
          AND trim(COALESCE(pig.gpc_brick_code, '')) <> ''
        ORDER BY
            {confirmed_sql} DESC,
            {confidence_sql} DESC,
            pgm.updated_at DESC
        LIMIT 1
    """), {"global_product_id": global_product_id}).mappings().first()
    return dict(row) if row else None


def _migration_suppressed(conn, global_product_id: str) -> bool:
    return bool(conn.execute(text(
        "SELECT 1 FROM global_product_gpc_migration_suppressions "
        "WHERE global_product_id = :id LIMIT 1"
    ), {"id": global_product_id}).first())


def _migrate_confirmed_legacy_assignment(conn, global_product_id: str) -> dict[str, Any] | None:
    if _assignment_row(conn, global_product_id) or _migration_suppressed(conn, global_product_id):
        return None
    candidate = _legacy_candidate(conn, global_product_id)
    if not candidate or not bool(candidate.get("confirmed_by_user")):
        return None
    conn.execute(text("""
        INSERT INTO global_product_gpc_bricks (
            global_product_id, brick_code, assignment_source,
            confidence, migrated_from, updated_at
        ) VALUES (
            :global_product_id, :brick_code, 'migrated_confirmed_product_group',
            :confidence, :migrated_from, CURRENT_TIMESTAMP
        )
        ON CONFLICT(global_product_id) DO NOTHING
    """), {
        "global_product_id": global_product_id,
        "brick_code": candidate["brick_code"],
        "confidence": float(candidate.get("confidence") or 1.0),
        "migrated_from": str(candidate.get("inventory_group_key") or candidate.get("legacy_source") or ""),
    })
    return candidate


def _metadata_suggestion(conn, global_product_id: str) -> dict[str, Any] | None:
    legacy = _legacy_candidate(conn, global_product_id)
    if legacy:
        row = conn.execute(
            text(_brick_select_sql("WHERE b.brick_code = :brick_code")),
            {"brick_code": legacy["brick_code"]},
        ).mappings().first()
        if row:
            result = dict(row)
            result.update({
                "suggestion_source": "bestaande_productgroep",
                "suggestion_reason": "Bestaande GPC-productgroep bij dit catalogusartikel",
                "confidence": float(legacy.get("confidence") or 0.0),
            })
            return result

    product = conn.execute(text("""
        SELECT id, name, brand, category, primary_gtin
        FROM global_products
        WHERE id = :id
        LIMIT 1
    """), {"id": global_product_id}).mappings().first()
    if not product:
        return None

    metadata_parts = [product.get("name"), product.get("brand"), product.get("category")]
    if "external_product_index" in _tables() and product.get("primary_gtin"):
        external = conn.execute(text("""
            SELECT product_name, brand, category, categories, product_type, search_terms
            FROM external_product_index
            WHERE gtin = :gtin OR ean = :gtin OR code = :gtin
            ORDER BY updated_at DESC
            LIMIT 1
        """), {"gtin": product.get("primary_gtin")}).mappings().first()
        if external:
            metadata_parts.extend(external.values())

    stopwords = {"kids", "pizza", "biologisch", "organic", "the", "and", "voor", "met", "van"}
    tokens = []
    for token in re.findall(r"[a-z0-9]+", " ".join(str(value or "") for value in metadata_parts).lower()):
        if len(token) >= 4 and token not in stopwords and token not in tokens:
            tokens.append(token)
    if not tokens:
        return None

    candidates = conn.execute(text(_brick_select_sql() + " ORDER BY b.brick_code")).mappings().all()
    best = None
    best_score = 0
    matched_tokens: list[str] = []
    for candidate in candidates:
        haystack = " ".join(str(candidate.get(key) or "").lower() for key in (
            "brick_description", "brick_description_en", "class_description",
            "family_description", "segment_description",
        ))
        matches = [token for token in tokens if token in haystack]
        score = len(matches)
        if score > best_score:
            best = dict(candidate)
            best_score = score
            matched_tokens = matches
    if not best or best_score < 1:
        return None
    best.update({
        "suggestion_source": "productmetadata",
        "suggestion_reason": "Overeenkomst met productgegevens: " + ", ".join(matched_tokens[:5]),
        "confidence": min(0.85, 0.45 + (0.1 * best_score)),
    })
    return best


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
        migration = _migrate_confirmed_legacy_assignment(conn, global_product_id)
        row = _assignment_row(conn, global_product_id)
        suggestion = None if row else _metadata_suggestion(conn, global_product_id)
    return {
        "assignment": dict(row) if row else None,
        "suggestion": suggestion,
        "migration": {
            "performed": bool(migration),
            "source": "bevestigde bestaande productgroep" if migration else None,
        },
    }


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
        conn.execute(text("DELETE FROM global_product_gpc_migration_suppressions WHERE global_product_id = :id"), {"id": global_product_id})
        conn.execute(text("""
            INSERT INTO global_product_gpc_bricks (
                global_product_id, brick_code, assignment_source,
                confidence, migrated_from, updated_at
            ) VALUES (
                :global_product_id, :brick_code, 'manual_catalog_detail',
                1.0, NULL, CURRENT_TIMESTAMP
            )
            ON CONFLICT(global_product_id) DO UPDATE SET
                brick_code = excluded.brick_code,
                assignment_source = excluded.assignment_source,
                confidence = excluded.confidence,
                migrated_from = NULL,
                updated_at = CURRENT_TIMESTAMP
        """), {
            "global_product_id": global_product_id,
            "brick_code": brick_code,
        })
        row = _assignment_row(conn, global_product_id)
    return {"status": "success", "assignment": dict(row), "suggestion": None}


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
        conn.execute(text("""
            INSERT INTO global_product_gpc_migration_suppressions (global_product_id, created_at)
            VALUES (:id, CURRENT_TIMESTAMP)
            ON CONFLICT(global_product_id) DO UPDATE SET created_at = CURRENT_TIMESTAMP
        """), {"id": global_product_id})
    return {"status": "success", "assignment": None, "suggestion": None}
