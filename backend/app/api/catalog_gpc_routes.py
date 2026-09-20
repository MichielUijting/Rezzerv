from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text

from app.db import engine
from app.services.gpc_candidate_service import (
    build_product_signals,
    rank_gpc_candidates,
)
from app.services.gpc_reference_catalog_service import (
    bundled_official_gpc_bricks,
    ensure_official_gpc_brick,
    search_official_gpc_bricks,
)


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
    inspector = inspect(engine)
    required_tables = {
        "global_product_gpc_bricks",
        "global_product_gpc_migration_suppressions",
    }
    missing_tables = sorted(required_tables - set(inspector.get_table_names()))
    if missing_tables:
        raise RuntimeError(
            "Canonical catalog GPC assignment schema ontbreekt: "
            + ", ".join(missing_tables)
            + ". Voer Alembic migrations uit."
        )
    assignment_columns = {
        "global_product_id",
        "brick_code",
        "assignment_source",
        "confidence",
        "migrated_from",
        "updated_at",
    }
    actual_assignment_columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns("global_product_gpc_bricks")
    }
    missing_assignment_columns = sorted(assignment_columns - actual_assignment_columns)
    if missing_assignment_columns:
        raise RuntimeError(
            "global_product_gpc_bricks mist canonical kolommen: "
            + ", ".join(missing_assignment_columns)
        )
    suppression_columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns("global_product_gpc_migration_suppressions")
    }
    if not {"global_product_id", "created_at"}.issubset(suppression_columns):
        raise RuntimeError("global_product_gpc_migration_suppressions wijkt af")
    indexes = {
        str(index.get("name") or ""): tuple(index.get("column_names") or ())
        for index in inspector.get_indexes("global_product_gpc_bricks")
    }
    if indexes.get("idx_global_product_gpc_brick_code") != ("brick_code",):
        raise RuntimeError("Canonical GPC assignment-index ontbreekt of wijkt af")


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


def _external_product_metadata(conn, product: dict[str, Any]) -> dict[str, Any]:
    gtin = str(product.get("primary_gtin") or "").strip()
    if not gtin or "external_product_index" not in _tables():
        return {}

    available = _columns("external_product_index")
    identity_columns = [column for column in ("gtin", "ean", "code") if column in available]
    metadata_columns = [
        column
        for column in (
            "product_name",
            "brand",
            "category",
            "categories",
            "normalized_search_text",
            "retailer_code",
        )
        if column in available
    ]
    if not identity_columns or not metadata_columns:
        return {}

    where_clause = " OR ".join(f"{column} = :gtin" for column in identity_columns)
    order_clause = "updated_at DESC" if "updated_at" in available else "id"
    row = conn.execute(
        text(
            f"SELECT {', '.join(metadata_columns)} "
            f"FROM external_product_index "
            f"WHERE {where_clause} "
            f"ORDER BY {order_clause} LIMIT 1"
        ),
        {"gtin": gtin},
    ).mappings().first()
    return dict(row) if row else {}


def _candidate_catalog_rows(conn) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in conn.execute(
            text(_brick_select_sql() + " ORDER BY b.brick_code")
        ).mappings().all()
    ]
    known = {str(row.get("brick_code") or "") for row in rows}

    # De gebundelde GS1-referentie is de volledige officiële fallback.
    # Daardoor wordt kandidaatgeneratie niet beperkt door een partiële DB-import.
    for bundled in bundled_official_gpc_bricks():
        code = str(bundled.get("brick_code") or "")
        if not code or code in known:
            continue
        rows.append(dict(bundled))
        known.add(code)
    return rows


def _legacy_suggestion_row(
    conn,
    global_product_id: str,
    candidates_by_code: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    legacy = _legacy_candidate(conn, global_product_id)
    if not legacy:
        return None
    code = str(legacy.get("brick_code") or "").strip()
    row = candidates_by_code.get(code)
    if not row:
        return None

    confidence = max(0.0, min(1.0, float(legacy.get("confidence") or 0.0)))
    result = dict(row)
    result.update({
        "suggestion_source": "bestaande_productgroep",
        "suggestion_reason": "Bestaande GPC-productgroep bij dit catalogusartikel",
        "confidence": confidence,
        "confidence_label": "hoog" if confidence >= 0.78 else "redelijk" if confidence >= 0.58 else "laag",
        "match_strength_percent": int(round(confidence * 100)),
        "matched_terms": [],
        "intent_key": "",
    })
    return result


def _metadata_suggestions(
    conn,
    global_product_id: str,
    *,
    limit: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    product = conn.execute(text("""
        SELECT id, name, brand, category, primary_gtin
        FROM global_products
        WHERE id = :id
        LIMIT 1
    """), {"id": global_product_id}).mappings().first()
    if not product:
        return [], {"intent_key": "", "reference_count": 0}

    product_dict = dict(product)
    external = _external_product_metadata(conn, product_dict)
    signal_bundle = build_product_signals({
        "product_name": product_dict.get("name"),
        "category": product_dict.get("category"),
        "external_product_name": external.get("product_name"),
        "external_category": external.get("category"),
        "external_categories": external.get("categories"),
        "external_search_text": external.get("normalized_search_text"),
    })

    candidate_rows = _candidate_catalog_rows(conn)
    ranked = rank_gpc_candidates(
        candidate_rows,
        signal_bundle,
        limit=max(1, min(int(limit), 5)),
    )

    by_code = {
        str(row.get("brick_code") or ""): row
        for row in candidate_rows
        if str(row.get("brick_code") or "")
    }
    legacy = _legacy_suggestion_row(conn, global_product_id, by_code)
    if legacy:
        legacy_code = str(legacy.get("brick_code") or "")
        ranked = [
            legacy,
            *[
                candidate
                for candidate in ranked
                if str(candidate.get("brick_code") or "") != legacy_code
            ],
        ][: max(1, min(int(limit), 5))]

    return ranked, {
        "intent_key": str(signal_bundle.get("intent_key") or ""),
        "reference_count": len(candidate_rows),
        "signal_count": len(signal_bundle.get("signals") or []),
        "external_metadata_found": bool(external),
    }


@router.get("/gpc/bricks")
def search_catalog_gpc_bricks(
    query: str = Query(default="", max_length=200),
    limit: int = Query(default=25, ge=1, le=100),
):
    _require_gpc_tables()
    normalized = " ".join(str(query or "").strip().split()).lower()
    with engine.begin() as conn:
        rows = search_official_gpc_bricks(
            conn,
            query=normalized,
            limit=int(limit),
        )
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
        suggestions: list[dict[str, Any]] = []
        candidate_generation = {
            "intent_key": "",
            "reference_count": 0,
            "signal_count": 0,
            "external_metadata_found": False,
        }
        if not row:
            suggestions, candidate_generation = _metadata_suggestions(
                conn,
                global_product_id,
                limit=5,
            )
    return {
        "assignment": dict(row) if row else None,
        "suggestion": suggestions[0] if suggestions else None,
        "suggestions": suggestions,
        "candidate_generation": candidate_generation,
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
        if not ensure_official_gpc_brick(conn, brick_code):
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
