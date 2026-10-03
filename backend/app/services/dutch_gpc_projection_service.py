from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import inspect, text, bindparam
from sqlalchemy.engine import Connection

from app.services.gpc_candidate_service import build_product_signals, rank_gpc_candidates


def _tables(conn: Connection) -> set[str]:
    return set(inspect(conn).get_table_names())


def _active_clause(conn: Connection, alias: str) -> str:
    if conn.dialect.name == "postgresql":
        return f"COALESCE({alias}.active, TRUE) IS TRUE"
    return f"COALESCE({alias}.active, 1) = 1"


def _normalize_ids(values: Iterable[Any]) -> list[str]:
    return sorted({
        str(value or "").strip()
        for value in values
        if str(value or "").strip()
    })


def _row_payload(row: Any) -> dict[str, str]:
    return {
        "gpc_brick_code": str(row.get("gpc_brick_code") or "").strip(),
        "gpc_brick_name": str(row.get("gpc_brick_name") or "").strip(),
        "gpc_class_code": str(row.get("gpc_class_code") or "").strip(),
        "gpc_class_name": str(row.get("gpc_class_name") or "").strip(),
        "gpc_family_code": str(row.get("gpc_family_code") or "").strip(),
        "gpc_family_name": str(row.get("gpc_family_name") or "").strip(),
        "gpc_segment_code": str(row.get("gpc_segment_code") or "").strip(),
        "gpc_segment_name": str(row.get("gpc_segment_name") or "").strip(),
    }


def _translated_text(conn: Connection, entity_type: str, code: str, fallback: str) -> str:
    if "gpc_translations" not in _tables(conn):
        return str(fallback or "").strip()
    row = conn.execute(text("""
        SELECT translated_text
        FROM gpc_translations
        WHERE entity_type = :entity_type
          AND entity_code = :entity_code
          AND lower(language_code) = 'nl'
        LIMIT 1
    """), {"entity_type": entity_type, "entity_code": str(code or "").strip()}).mappings().first()
    return str((row or {}).get("translated_text") or fallback or "").strip()


def _canonical_hierarchy_by_brick(conn: Connection, brick_codes: Iterable[Any]) -> dict[str, dict[str, str]]:
    codes = _normalize_ids(brick_codes)
    required = {"gpc_bricks", "gpc_classes", "gpc_families", "gpc_segments"}
    if not codes or not required.issubset(_tables(conn)):
        return {}

    rows = conn.execute(
        text("""
            SELECT
                b.brick_code AS gpc_brick_code,
                b.description AS brick_description,
                c.class_code AS gpc_class_code,
                c.description AS class_description,
                f.family_code AS gpc_family_code,
                f.description AS family_description,
                s.segment_code AS gpc_segment_code,
                s.description AS segment_description
            FROM gpc_bricks b
            JOIN gpc_classes c ON c.class_code = b.class_code
            JOIN gpc_families f ON f.family_code = c.family_code
            JOIN gpc_segments s ON s.segment_code = f.segment_code
            WHERE b.brick_code IN :brick_codes
        """).bindparams(bindparam("brick_codes", expanding=True)),
        {"brick_codes": codes},
    ).mappings().all()

    result: dict[str, dict[str, str]] = {}
    for row in rows:
        brick_code = str(row.get("gpc_brick_code") or "").strip()
        if not brick_code:
            continue
        result[brick_code] = {
            "gpc_brick_code": brick_code,
            "gpc_brick_name": _translated_text(conn, "brick", brick_code, row.get("brick_description")),
            "gpc_class_code": str(row.get("gpc_class_code") or "").strip(),
            "gpc_class_name": _translated_text(conn, "class", row.get("gpc_class_code"), row.get("class_description")),
            "gpc_family_code": str(row.get("gpc_family_code") or "").strip(),
            "gpc_family_name": _translated_text(conn, "family", row.get("gpc_family_code"), row.get("family_description")),
            "gpc_segment_code": str(row.get("gpc_segment_code") or "").strip(),
            "gpc_segment_name": _translated_text(conn, "segment", row.get("gpc_segment_code"), row.get("segment_description")),
        }
    return result


def _candidate_rows(conn: Connection) -> list[dict[str, Any]]:
    if "gpc_product_groups" not in _tables(conn):
        return []
    rows = conn.execute(text(f"""
        SELECT
            nl.gpc_brick_code AS brick_code,
            nl.gpc_brick_name AS brick_description,
            nl.gpc_class_code AS class_code,
            nl.gpc_class_name AS class_description,
            nl.gpc_family_code AS family_code,
            nl.gpc_family_name AS family_description,
            nl.gpc_segment_code AS segment_code,
            nl.gpc_segment_name AS segment_description
        FROM gpc_product_groups nl
        WHERE lower(COALESCE(nl.language_code, '')) = 'nl'
          AND {_active_clause(conn, 'nl')}
          AND trim(COALESCE(nl.gpc_brick_code, '')) <> ''
          AND trim(COALESCE(nl.gpc_brick_name, '')) <> ''
          AND trim(COALESCE(nl.gpc_family_name, '')) <> ''
        ORDER BY nl.gpc_brick_name, nl.gpc_brick_code
    """)).mappings().all()
    return [dict(row) for row in rows]


def _legacy_brick_by_product(conn: Connection, ids: list[str]) -> dict[str, dict[str, Any]]:
    required = {"product_group_memberships", "product_inventory_groups"}
    if not ids or not required.issubset(_tables(conn)):
        return {}
    pgm_columns = {str(col.get("name") or "") for col in inspect(conn).get_columns("product_group_memberships")}
    pig_columns = {str(col.get("name") or "") for col in inspect(conn).get_columns("product_inventory_groups")}
    if not {"global_product_id", "inventory_group_key"}.issubset(pgm_columns):
        return {}
    if not {"inventory_group_key", "gpc_brick_code"}.issubset(pig_columns):
        return {}
    confidence_sql = "COALESCE(pgm.confidence, 0.85)" if "confidence" in pgm_columns else "0.85"
    active_sql = "COALESCE(pgm.active, 1) = 1" if "active" in pgm_columns else "1 = 1"
    rows = conn.execute(
        text(f"""
            SELECT
                CAST(pgm.global_product_id AS TEXT) AS global_product_id,
                pig.gpc_brick_code AS brick_code,
                {confidence_sql} AS confidence
            FROM product_group_memberships pgm
            JOIN product_inventory_groups pig
              ON pig.inventory_group_key = pgm.inventory_group_key
            WHERE CAST(pgm.global_product_id AS TEXT) IN :global_product_ids
              AND {active_sql}
              AND trim(COALESCE(pig.gpc_brick_code, '')) <> ''
            ORDER BY {confidence_sql} DESC
        """).bindparams(bindparam("global_product_ids", expanding=True)),
        {"global_product_ids": ids},
    ).mappings().all()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        product_id = str(row.get("global_product_id") or "").strip()
        if product_id and product_id not in result:
            result[product_id] = dict(row)
    return result


def ensure_dutch_gpc_assignments(
    conn: Connection,
    global_product_ids: Iterable[Any],
) -> dict[str, int]:
    ids = _normalize_ids(global_product_ids)
    required = {"global_products", "global_product_gpc_bricks", "gpc_product_groups"}
    if not ids or not required.issubset(_tables(conn)):
        return {"requested": len(ids), "existing": 0, "assigned": 0, "unresolved": len(ids)}

    existing_rows = conn.execute(
        text("""
            SELECT CAST(global_product_id AS TEXT) AS global_product_id
            FROM global_product_gpc_bricks
            WHERE CAST(global_product_id AS TEXT) IN :global_product_ids
        """).bindparams(bindparam("global_product_ids", expanding=True)),
        {"global_product_ids": ids},
    ).mappings().all()
    existing = {str(row.get("global_product_id") or "").strip() for row in existing_rows}
    missing = [product_id for product_id in ids if product_id not in existing]
    if not missing:
        return {"requested": len(ids), "existing": len(existing), "assigned": 0, "unresolved": 0}

    legacy = _legacy_brick_by_product(conn, missing)
    assigned = 0
    still_missing: list[str] = []
    for product_id in missing:
        legacy_row = legacy.get(product_id)
        if not legacy_row:
            still_missing.append(product_id)
            continue
        conn.execute(text("""
            INSERT INTO global_product_gpc_bricks (
                global_product_id, brick_code, assignment_source,
                confidence, migrated_from, updated_at
            ) VALUES (
                :global_product_id, :brick_code, 'auto_existing_product_group',
                :confidence, 'product_group_membership', CURRENT_TIMESTAMP
            )
            ON CONFLICT(global_product_id) DO NOTHING
        """), {
            "global_product_id": product_id,
            "brick_code": str(legacy_row.get("brick_code") or "").strip(),
            "confidence": float(legacy_row.get("confidence") or 0.85),
        })
        assigned += 1

    if still_missing:
        product_columns = {str(col.get("name") or "") for col in inspect(conn).get_columns("global_products")}
        category_sql = "gp.category" if "category" in product_columns else "NULL"
        rows = conn.execute(
            text(f"""
                SELECT
                    CAST(gp.id AS TEXT) AS id,
                    gp.name,
                    {category_sql} AS category
                FROM global_products gp
                WHERE CAST(gp.id AS TEXT) IN :global_product_ids
            """).bindparams(bindparam("global_product_ids", expanding=True)),
            {"global_product_ids": still_missing},
        ).mappings().all()
        candidates = _candidate_rows(conn)
        for row in rows:
            product_id = str(row.get("id") or "").strip()
            signal_bundle = build_product_signals({
                "product_name": row.get("name"),
                "category": row.get("category"),
            })
            ranked = rank_gpc_candidates(candidates, signal_bundle, limit=1)
            if not ranked:
                continue
            best = ranked[0]
            brick_code = str(best.get("brick_code") or "").strip()
            if not brick_code:
                continue
            conn.execute(text("""
                INSERT INTO global_product_gpc_bricks (
                    global_product_id, brick_code, assignment_source,
                    confidence, migrated_from, updated_at
                ) VALUES (
                    :global_product_id, :brick_code, 'auto_dutch_gpc_candidate',
                    :confidence, 'dutch_gpc_product_name', CURRENT_TIMESTAMP
                )
                ON CONFLICT(global_product_id) DO NOTHING
            """), {
                "global_product_id": product_id,
                "brick_code": brick_code,
                "confidence": float(best.get("confidence") or 0.30),
            })
            assigned += 1

    unresolved = max(0, len(ids) - len(existing) - assigned)
    return {
        "requested": len(ids),
        "existing": len(existing),
        "assigned": assigned,
        "unresolved": unresolved,
    }


def dutch_gpc_by_global_product(
    conn: Connection,
    global_product_ids: Iterable[Any],
) -> dict[str, dict[str, str]]:
    ids = _normalize_ids(global_product_ids)
    if not ids or "global_product_gpc_bricks" not in _tables(conn):
        return {}

    ensure_dutch_gpc_assignments(conn, ids)

    rows = conn.execute(
        text("""
            SELECT
                CAST(global_product_id AS TEXT) AS global_product_id,
                brick_code
            FROM global_product_gpc_bricks
            WHERE CAST(global_product_id AS TEXT) IN :global_product_ids
        """).bindparams(bindparam("global_product_ids", expanding=True)),
        {"global_product_ids": ids},
    ).mappings().all()
    hierarchy = _canonical_hierarchy_by_brick(
        conn,
        [row.get("brick_code") for row in rows],
    )

    result: dict[str, dict[str, str]] = {}
    unresolved: list[dict[str, Any]] = []
    for row in rows:
        product_id = str(row.get("global_product_id") or "").strip()
        brick_code = str(row.get("brick_code") or "").strip()
        payload = hierarchy.get(brick_code)
        if product_id and payload:
            result[product_id] = payload
        elif product_id and brick_code:
            unresolved.append(dict(row))

    # Compatibiliteit met databases waarin de Nederlandse GPC-hiërarchie
    # rechtstreeks in gpc_product_groups staat.
    if unresolved and "gpc_product_groups" in _tables(conn):
        legacy_rows = conn.execute(
            text(f"""
                SELECT
                    CAST(a.global_product_id AS TEXT) AS global_product_id,
                    nl.gpc_brick_code,
                    nl.gpc_brick_name,
                    nl.gpc_class_code,
                    nl.gpc_class_name,
                    nl.gpc_family_code,
                    nl.gpc_family_name,
                    nl.gpc_segment_code,
                    nl.gpc_segment_name
                FROM global_product_gpc_bricks a
                JOIN gpc_product_groups nl
                  ON nl.gpc_brick_code = a.brick_code
                 AND lower(COALESCE(nl.language_code, '')) = 'nl'
                 AND {_active_clause(conn, 'nl')}
                WHERE CAST(a.global_product_id AS TEXT) IN :global_product_ids
            """).bindparams(bindparam("global_product_ids", expanding=True)),
            {"global_product_ids": [row["global_product_id"] for row in unresolved]},
        ).mappings().all()
        for row in legacy_rows:
            product_id = str(row.get("global_product_id") or "").strip()
            if product_id:
                result[product_id] = _row_payload(row)
    return result


def dutch_gpc_by_household_article(
    conn: Connection,
    household_id: str,
    household_article_ids: Iterable[Any],
) -> dict[str, dict[str, str]]:
    ids = _normalize_ids(household_article_ids)
    if not ids or "household_articles" not in _tables(conn):
        return {}

    columns = {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns("household_articles")
    }
    direct_brick_sql = (
        "ha.representative_image_gpc_brick_code"
        if "representative_image_gpc_brick_code" in columns
        else "NULL"
    )
    global_product_sql = "ha.global_product_id" if "global_product_id" in columns else "NULL"

    rows = conn.execute(
        text(f"""
            SELECT
                CAST(ha.id AS TEXT) AS household_article_id,
                CAST({global_product_sql} AS TEXT) AS global_product_id,
                {direct_brick_sql} AS direct_brick_code
            FROM household_articles ha
            WHERE ha.household_id = :household_id
              AND CAST(ha.id AS TEXT) IN :household_article_ids
        """).bindparams(bindparam("household_article_ids", expanding=True)),
        {"household_id": str(household_id), "household_article_ids": ids},
    ).mappings().all()

    product_ids = [row.get("global_product_id") for row in rows if row.get("global_product_id")]

    # Oudere huishoudartikelen kunnen via product_identities wel een canoniek
    # product hebben terwijl household_articles.global_product_id nog leeg is.
    identity_by_article: dict[str, str] = {}
    if "product_identities" in _tables(conn):
        pi_columns = {
            str(column.get("name") or "")
            for column in inspect(conn).get_columns("product_identities")
        }
        if {"household_article_id", "global_product_id"}.issubset(pi_columns):
            identity_rows = conn.execute(
                text("""
                    SELECT
                        CAST(household_article_id AS TEXT) AS household_article_id,
                        CAST(global_product_id AS TEXT) AS global_product_id
                    FROM product_identities
                    WHERE CAST(household_article_id AS TEXT) IN :household_article_ids
                      AND global_product_id IS NOT NULL
                    ORDER BY COALESCE(is_primary, 0) DESC, created_at DESC
                """).bindparams(bindparam("household_article_ids", expanding=True)),
                {"household_article_ids": ids},
            ).mappings().all()
            for identity in identity_rows:
                article_id = str(identity.get("household_article_id") or "").strip()
                product_id = str(identity.get("global_product_id") or "").strip()
                if article_id and product_id and article_id not in identity_by_article:
                    identity_by_article[article_id] = product_id
                    product_ids.append(product_id)

    product_projection = dutch_gpc_by_global_product(conn, product_ids)
    direct_hierarchy = _canonical_hierarchy_by_brick(
        conn,
        [row.get("direct_brick_code") for row in rows if row.get("direct_brick_code")],
    )

    result: dict[str, dict[str, str]] = {}
    for row in rows:
        article_id = str(row.get("household_article_id") or "").strip()
        product_id = (
            str(row.get("global_product_id") or "").strip()
            or identity_by_article.get(article_id, "")
        )
        direct_brick_code = str(row.get("direct_brick_code") or "").strip()
        payload = product_projection.get(product_id) if product_id else None
        if not payload and direct_brick_code:
            payload = direct_hierarchy.get(direct_brick_code)
        if article_id and payload:
            result[article_id] = payload
    return result
