from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, text


REPRESENTATIVE_IMAGE_COLUMNS = {
    "representative_image_url",
    "representative_image_global_product_id",
    "representative_image_gpc_brick_code",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _tables(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _columns(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if not inspector.has_table(table_name):
        return set()
    return {str(column.get("name") or "") for column in inspector.get_columns(table_name)}


def _representative_schema_ready(conn) -> bool:
    return REPRESENTATIVE_IMAGE_COLUMNS.issubset(_columns(conn, "household_articles"))


def _product_image_and_brick(conn, global_product_id: Any) -> dict[str, str]:
    product_id = _clean(global_product_id)
    if not product_id:
        return {}
    row = conn.execute(
        text(
            """
            SELECT
                gp.id AS global_product_id,
                COALESCE(gp.image_url, '') AS image_url,
                COALESCE(gpb.brick_code, '') AS gpc_brick_code
            FROM global_products gp
            LEFT JOIN global_product_gpc_bricks gpb
              ON gpb.global_product_id = gp.id
            WHERE gp.id = :global_product_id
              AND lower(COALESCE(gp.status, 'active')) = 'active'
            ORDER BY gpb.brick_code
            LIMIT 1
            """
        ),
        {"global_product_id": product_id},
    ).mappings().first()
    return dict(row or {})


def _unique_brick_for_article_group(conn, article_group_id: Any) -> str:
    group_id = _clean(article_group_id)
    if not group_id or "gpc_bricks" not in _tables(conn):
        return ""

    translation_join = ""
    translation_match = "FALSE"
    if "gpc_translations" in _tables(conn):
        translation_join = """
            LEFT JOIN gpc_translations tr
              ON tr.entity_type = 'brick'
             AND tr.entity_code = gb.brick_code
             AND tr.language_code = 'nl'
        """
        translation_match = "lower(trim(COALESCE(tr.translated_text, ''))) = lower(trim(ag.name))"

    rows = conn.execute(
        text(
            f"""
            SELECT DISTINCT gb.brick_code
            FROM article_groups ag
            JOIN gpc_bricks gb
              ON lower(trim(COALESCE(gb.description, ''))) = lower(trim(ag.name))
              OR ({translation_match})
            {translation_join}
            WHERE ag.id = :article_group_id
              AND COALESCE(trim(ag.name), '') <> ''
            ORDER BY gb.brick_code
            """
        ),
        {"article_group_id": group_id},
    ).mappings().all()
    brick_codes = [_clean(row.get("brick_code")) for row in rows if _clean(row.get("brick_code"))]
    return brick_codes[0] if len(set(brick_codes)) == 1 else ""


def _latest_exact_history_candidate(
    conn,
    household_article_id: str,
    required_brick_code: str,
) -> dict[str, str]:
    tables = _tables(conn)
    columns = _columns(conn, "purchase_import_lines")
    required_columns = {"matched_household_article_id", "matched_global_product_id"}
    if "purchase_import_lines" not in tables or not required_columns.issubset(columns):
        return {}

    brick_condition = ""
    params: dict[str, Any] = {"household_article_id": household_article_id}
    if required_brick_code:
        brick_condition = "AND gpb.brick_code = :required_brick_code"
        params["required_brick_code"] = required_brick_code

    order_expression = (
        "COALESCE(pil.updated_at, pil.created_at)"
        if {"updated_at", "created_at"}.issubset(columns)
        else "pil.created_at"
        if "created_at" in columns
        else "pil.id"
    )
    row = conn.execute(
        text(
            f"""
            SELECT
                gp.id AS global_product_id,
                COALESCE(gp.image_url, '') AS image_url,
                COALESCE(gpb.brick_code, '') AS gpc_brick_code
            FROM purchase_import_lines pil
            JOIN global_products gp
              ON gp.id = pil.matched_global_product_id
            LEFT JOIN global_product_gpc_bricks gpb
              ON gpb.global_product_id = gp.id
            WHERE pil.matched_household_article_id = :household_article_id
              AND pil.matched_global_product_id IS NOT NULL
              AND COALESCE(trim(gp.primary_gtin), '') <> ''
              AND COALESCE(trim(gp.image_url), '') <> ''
              AND lower(COALESCE(gp.status, 'active')) = 'active'
              {brick_condition}
            ORDER BY {order_expression} DESC, gp.id ASC
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    return dict(row or {})


def _brick_representative_candidate(conn, brick_code: str) -> dict[str, str]:
    normalized_brick = _clean(brick_code)
    if not normalized_brick:
        return {}
    row = conn.execute(
        text(
            """
            SELECT
                gp.id AS global_product_id,
                COALESCE(gp.image_url, '') AS image_url,
                gpb.brick_code AS gpc_brick_code
            FROM global_product_gpc_bricks gpb
            JOIN global_products gp ON gp.id = gpb.global_product_id
            WHERE gpb.brick_code = :brick_code
              AND COALESCE(trim(gp.primary_gtin), '') <> ''
              AND COALESCE(trim(gp.image_url), '') <> ''
              AND lower(COALESCE(gp.status, 'active')) = 'active'
            ORDER BY gp.updated_at DESC, gp.created_at DESC, gp.id ASC
            LIMIT 1
            """
        ),
        {"brick_code": normalized_brick},
    ).mappings().first()
    return dict(row or {})


def _resolve_representative_candidate(conn, article: dict[str, Any]) -> dict[str, str]:
    existing_url = _clean(article.get("representative_image_url"))
    if existing_url:
        return {
            "image_url": existing_url,
            "global_product_id": _clean(article.get("representative_image_global_product_id")),
            "gpc_brick_code": _clean(article.get("representative_image_gpc_brick_code")),
        }

    direct = _product_image_and_brick(conn, article.get("global_product_id"))
    article_brick = _clean(direct.get("gpc_brick_code"))
    if not article_brick:
        article_brick = _unique_brick_for_article_group(conn, article.get("article_group_id"))

    if _clean(direct.get("image_url")):
        return {
            "image_url": _clean(direct.get("image_url")),
            "global_product_id": _clean(direct.get("global_product_id")),
            "gpc_brick_code": article_brick,
        }

    article_id = _clean(article.get("id"))
    history = _latest_exact_history_candidate(conn, article_id, article_brick)
    if _clean(history.get("image_url")):
        return {
            "image_url": _clean(history.get("image_url")),
            "global_product_id": _clean(history.get("global_product_id")),
            "gpc_brick_code": _clean(history.get("gpc_brick_code")) or article_brick,
        }

    if article_brick:
        brick_candidate = _brick_representative_candidate(conn, article_brick)
        if _clean(brick_candidate.get("image_url")):
            return {
                "image_url": _clean(brick_candidate.get("image_url")),
                "global_product_id": _clean(brick_candidate.get("global_product_id")),
                "gpc_brick_code": article_brick,
            }

    return {}


def materialize_household_representative_images(
    conn,
    household_article_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, str]:
    """Persist one stable representative image per household article.

    Product/store identifiers may differ. GPC Brick is used as a compatibility
    boundary; the chosen image is persisted on household_articles so Voorraad stays
    visually stable across later purchases from other retailers.
    """
    if not _representative_schema_ready(conn):
        return {}

    filters = ["COALESCE(trim(ha.representative_image_url), '') = ''"]
    params: dict[str, Any] = {}
    normalized_ids = []
    for value in household_article_ids or []:
        article_id = _clean(value)
        if article_id and article_id not in normalized_ids:
            normalized_ids.append(article_id)
    if normalized_ids:
        placeholders = ", ".join(f":article_id_{index}" for index in range(len(normalized_ids)))
        filters.append(f"ha.id IN ({placeholders})")
        params.update({f"article_id_{index}": value for index, value in enumerate(normalized_ids)})

    rows = conn.execute(
        text(
            f"""
            SELECT
                ha.id,
                ha.household_id,
                ha.global_product_id,
                ha.article_group_id,
                ha.representative_image_url,
                ha.representative_image_global_product_id,
                ha.representative_image_gpc_brick_code
            FROM household_articles ha
            WHERE {' AND '.join(filters)}
            ORDER BY ha.id
            """
        ),
        params,
    ).mappings().all()

    resolved: dict[str, str] = {}
    for raw_row in rows:
        article = dict(raw_row)
        article_id = _clean(article.get("id"))
        candidate = _resolve_representative_candidate(conn, article)
        image_url = _clean(candidate.get("image_url"))
        if not article_id or not image_url:
            continue
        conn.execute(
            text(
                """
                UPDATE household_articles
                SET representative_image_url = :image_url,
                    representative_image_global_product_id = :global_product_id,
                    representative_image_gpc_brick_code = :gpc_brick_code
                WHERE id = :household_article_id
                  AND COALESCE(trim(representative_image_url), '') = ''
                """
            ),
            {
                "household_article_id": article_id,
                "image_url": image_url,
                "global_product_id": _clean(candidate.get("global_product_id")) or None,
                "gpc_brick_code": _clean(candidate.get("gpc_brick_code")) or None,
            },
        )
        resolved[article_id] = image_url
    return resolved


def backfill_household_representative_images(engine) -> int:
    with engine.begin() as conn:
        return len(materialize_household_representative_images(conn))
