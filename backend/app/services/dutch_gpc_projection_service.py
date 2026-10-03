from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import inspect, text, bindparam
from sqlalchemy.engine import Connection

from app.services.gpc_candidate_service import build_product_signals, rank_gpc_candidates


BUNDLED_DUTCH_GPC_PATH = Path(__file__).resolve().parent.parent / "data" / "gpc_bricks_nl.json"


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


def ensure_bundled_dutch_gpc_reference(conn: Connection) -> dict[str, int | str]:
    """Vul de Nederlandse GPC-referentie uit het meegeleverde officiële bestand.

    Dit is uitsluitend referentiedata-DML. Het maakt of wijzigt geen schema en
    wijzigt geen huishoud-, voorraad- of kassabongegevens.
    """
    if "gpc_product_groups" not in _tables(conn) or not BUNDLED_DUTCH_GPC_PATH.is_file():
        return {"expected": 0, "loaded": 0, "source_version": ""}

    columns = {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns("gpc_product_groups")
    }
    required = {
        "gpc_brick_code",
        "gpc_brick_name",
        "gpc_class_code",
        "gpc_class_name",
        "gpc_family_code",
        "gpc_family_name",
        "gpc_segment_code",
        "gpc_segment_name",
        "language_code",
        "source_version",
        "active",
        "created_at",
        "updated_at",
    }
    if not required.issubset(columns):
        return {"expected": 0, "loaded": 0, "source_version": ""}

    payload = json.loads(BUNDLED_DUTCH_GPC_PATH.read_text(encoding="utf-8"))
    rows = list(payload.get("bricks") or [])
    source_version = str(payload.get("publication_version") or "").strip()
    expected = int(payload.get("brick_count") or len(rows))
    if not rows or expected != len(rows) or not source_version:
        raise RuntimeError("Meegeleverde Nederlandse GPC-referentie is ongeldig")

    already_loaded = int(conn.execute(text("""
        SELECT COUNT(*)
        FROM gpc_product_groups
        WHERE lower(COALESCE(language_code, '')) = 'nl'
          AND COALESCE(source_version, '') = :source_version
          AND COALESCE(active, TRUE) IS TRUE
    """), {"source_version": source_version}).scalar() or 0)
    if already_loaded >= expected:
        return {
            "expected": expected,
            "loaded": 0,
            "source_version": source_version,
        }

    params = []
    for row in rows:
        brick_code = str(row.get("gpc_brick_code") or "").strip()
        brick_name = str(row.get("gpc_brick_name") or "").strip()
        family_name = str(row.get("gpc_family_name") or "").strip()
        if not brick_code or not brick_name or not family_name:
            raise RuntimeError(
                f"Meegeleverde Nederlandse GPC-referentie is onvolledig voor Brick {brick_code or '?'}"
            )
        params.append({
            **row,
            "language_code": "nl",
            "source_version": source_version,
        })

    # global_product_gpc_bricks.brick_code heeft een FK naar gpc_bricks.
    # Daarom moet dezelfde officiële Nederlandse bundle eerst ook de canonieke
    # Segment -> Family -> Class -> Brick-tabellen vullen. Anders kan een
    # automatische Brick-toewijzing wel uit gpc_product_groups worden gekozen,
    # maar vervolgens op de FK naar gpc_bricks stuklopen.
    canonical_required = {"gpc_segments", "gpc_families", "gpc_classes", "gpc_bricks"}
    if canonical_required.issubset(_tables(conn)):
        segments = {}
        families = {}
        classes = {}
        bricks = {}
        for row in params:
            segments[row["gpc_segment_code"]] = {
                "segment_code": row["gpc_segment_code"],
                "description": row["gpc_segment_name"],
            }
            families[row["gpc_family_code"]] = {
                "family_code": row["gpc_family_code"],
                "description": row["gpc_family_name"],
                "segment_code": row["gpc_segment_code"],
            }
            classes[row["gpc_class_code"]] = {
                "class_code": row["gpc_class_code"],
                "description": row["gpc_class_name"],
                "family_code": row["gpc_family_code"],
            }
            bricks[row["gpc_brick_code"]] = {
                "brick_code": row["gpc_brick_code"],
                "description": row["gpc_brick_name"],
                "class_code": row["gpc_class_code"],
            }

        conn.execute(text("""
            INSERT INTO gpc_segments (segment_code, description)
            VALUES (:segment_code, :description)
            ON CONFLICT(segment_code) DO UPDATE SET
                description = excluded.description
        """), list(segments.values()))
        conn.execute(text("""
            INSERT INTO gpc_families (family_code, description, segment_code)
            VALUES (:family_code, :description, :segment_code)
            ON CONFLICT(family_code) DO UPDATE SET
                description = excluded.description,
                segment_code = excluded.segment_code
        """), list(families.values()))
        conn.execute(text("""
            INSERT INTO gpc_classes (class_code, description, family_code)
            VALUES (:class_code, :description, :family_code)
            ON CONFLICT(class_code) DO UPDATE SET
                description = excluded.description,
                family_code = excluded.family_code
        """), list(classes.values()))
        conn.execute(text("""
            INSERT INTO gpc_bricks (brick_code, description, class_code)
            VALUES (:brick_code, :description, :class_code)
            ON CONFLICT(brick_code) DO UPDATE SET
                description = excluded.description,
                class_code = excluded.class_code
        """), list(bricks.values()))

    conn.execute(text("""
        INSERT INTO gpc_product_groups (
            gpc_brick_code, gpc_brick_name,
            gpc_class_code, gpc_class_name,
            gpc_family_code, gpc_family_name,
            gpc_segment_code, gpc_segment_name,
            language_code, source_version, active, created_at, updated_at
        ) VALUES (
            :gpc_brick_code, :gpc_brick_name,
            :gpc_class_code, :gpc_class_name,
            :gpc_family_code, :gpc_family_name,
            :gpc_segment_code, :gpc_segment_name,
            :language_code, :source_version, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT(gpc_brick_code) DO UPDATE SET
            gpc_brick_name = excluded.gpc_brick_name,
            gpc_class_code = excluded.gpc_class_code,
            gpc_class_name = excluded.gpc_class_name,
            gpc_family_code = excluded.gpc_family_code,
            gpc_family_name = excluded.gpc_family_name,
            gpc_segment_code = excluded.gpc_segment_code,
            gpc_segment_name = excluded.gpc_segment_name,
            language_code = excluded.language_code,
            source_version = excluded.source_version,
            active = TRUE,
            updated_at = CURRENT_TIMESTAMP
    """), params)

    return {
        "expected": expected,
        "loaded": len(params),
        "source_version": source_version,
    }


def _canonical_hierarchy_by_brick(conn: Connection, brick_codes: Iterable[Any]) -> dict[str, dict[str, str]]:
    """Projecteer een bekende Brick rechtstreeks via de Nederlandse GS1-lijst.

    gpc_product_groups is de gebruikerszichtbare Nederlandse referentiebron:
    iedere rij bevat Brick, Class/Groep, Familie en Segment. Daardoor hoeft een
    bekende Brick niet eerst via de losse canonieke hiërarchietabellen te worden
    gereconstrueerd en kan dezelfde projectie overal worden hergebruikt.
    """
    codes = _normalize_ids(brick_codes)
    if not codes or "gpc_product_groups" not in _tables(conn):
        return {}

    rows = conn.execute(
        text(f"""
            SELECT
                gpg.gpc_brick_code,
                gpg.gpc_brick_name,
                gpg.gpc_class_code,
                gpg.gpc_class_name,
                gpg.gpc_family_code,
                gpg.gpc_family_name,
                gpg.gpc_segment_code,
                gpg.gpc_segment_name
            FROM gpc_product_groups gpg
            WHERE gpg.gpc_brick_code IN :brick_codes
              AND lower(COALESCE(gpg.language_code, '')) = 'nl'
              AND {_active_clause(conn, 'gpg')}
              AND trim(COALESCE(gpg.gpc_brick_name, '')) <> ''
              AND trim(COALESCE(gpg.gpc_class_name, '')) <> ''
              AND trim(COALESCE(gpg.gpc_family_name, '')) <> ''
              AND trim(COALESCE(gpg.gpc_segment_name, '')) <> ''
        """).bindparams(bindparam("brick_codes", expanding=True)),
        {"brick_codes": codes},
    ).mappings().all()

    result: dict[str, dict[str, str]] = {}
    for row in rows:
        brick_code = str(row.get("gpc_brick_code") or "").strip()
        if brick_code:
            result[brick_code] = _row_payload(row)
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
    ensure_bundled_dutch_gpc_reference(conn)
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
    ensure_bundled_dutch_gpc_reference(conn)
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
                    ORDER BY CASE WHEN is_primary THEN 1 ELSE 0 END DESC, created_at DESC
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
