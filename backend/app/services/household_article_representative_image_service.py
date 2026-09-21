"""Household-level representative Catalogus product for operational photos.

Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: choose and persist one representative exact Catalogus product
  for a household article, constrained by its official GS1 GPC Brick.
- Runtime Type: production
- Used By: runtime initialization and operational inventory projections
- Depends On: household_articles, global_products, global_product_gpc_bricks
- Reads Data: yes
- Writes Data: yes (explicit startup/backfill helper only)
- Status Authority: no
- Refactor Status: keep
"""
from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import text


REPRESENTATIVE_TABLE = "household_article_representative_products"


def _normalized(value: Any) -> str:
    return str(value or "").strip()


def _article_row(conn, household_article_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            """
            SELECT id, household_id, global_product_id, barcode
            FROM household_articles
            WHERE id = :household_article_id
            LIMIT 1
            """
        ),
        {"household_article_id": household_article_id},
    ).mappings().first()
    return dict(row) if row else None


def _direct_brick_code(conn, global_product_id: str) -> str:
    if not global_product_id:
        return ""
    row = conn.execute(
        text(
            """
            SELECT brick_code
            FROM global_product_gpc_bricks
            WHERE global_product_id = :global_product_id
            LIMIT 1
            """
        ),
        {"global_product_id": global_product_id},
    ).mappings().first()
    return _normalized((row or {}).get("brick_code"))


def _anchor_brick_code(conn, article: dict[str, Any]) -> str:
    """Resolve one safe Brick anchor for a household article.

    The direct household_article -> global_product classification is authoritative
    when available. Older articles may instead derive one unambiguous Brick from
    their canonical product identities or exact stored GTIN. Article names are
    deliberately never used.
    """
    article_id = _normalized(article.get("id"))
    direct_product_id = _normalized(article.get("global_product_id"))
    direct_brick = _direct_brick_code(conn, direct_product_id)
    if direct_brick:
        return direct_brick

    barcode = _normalized(article.get("barcode"))
    rows = conn.execute(
        text(
            """
            SELECT DISTINCT assignment.brick_code
            FROM product_identities identity_row
            JOIN global_product_gpc_bricks assignment
              ON assignment.global_product_id = identity_row.global_product_id
            WHERE identity_row.household_article_id = :household_article_id
              AND identity_row.global_product_id IS NOT NULL

            UNION

            SELECT DISTINCT assignment.brick_code
            FROM global_products gp
            JOIN global_product_gpc_bricks assignment
              ON assignment.global_product_id = gp.id
            WHERE :barcode <> ''
              AND gp.primary_gtin = :barcode
            """
        ),
        {
            "household_article_id": article_id,
            "barcode": barcode,
        },
    ).mappings().all()
    brick_codes = {
        _normalized(row.get("brick_code"))
        for row in rows
        if _normalized(row.get("brick_code"))
    }
    if len(brick_codes) == 1:
        return next(iter(brick_codes))
    return ""


def _representative_row(conn, household_article_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            f"""
            SELECT
                representative.household_article_id,
                representative.global_product_id,
                representative.brick_code,
                representative.selection_source,
                COALESCE(gp.image_url, '') AS image_url,
                COALESCE(gp.primary_gtin, '') AS primary_gtin,
                COALESCE(gp.status, 'active') AS product_status,
                COALESCE(assignment.brick_code, '') AS current_brick_code
            FROM {REPRESENTATIVE_TABLE} representative
            JOIN global_products gp
              ON gp.id = representative.global_product_id
            LEFT JOIN global_product_gpc_bricks assignment
              ON assignment.global_product_id = gp.id
            WHERE representative.household_article_id = :household_article_id
            LIMIT 1
            """
        ),
        {"household_article_id": household_article_id},
    ).mappings().first()
    return dict(row) if row else None


def _valid_representative(existing: dict[str, Any] | None, anchor_brick: str) -> bool:
    if not existing or not anchor_brick:
        return False
    return bool(
        _normalized(existing.get("brick_code")) == anchor_brick
        and _normalized(existing.get("current_brick_code")) == anchor_brick
        and _normalized(existing.get("image_url"))
        and _normalized(existing.get("primary_gtin"))
        and _normalized(existing.get("product_status")).lower() == "active"
    )


def _candidate_product(
    conn,
    *,
    household_article_id: str,
    direct_global_product_id: str,
    brick_code: str,
) -> dict[str, Any] | None:
    """Pick a stable exact Catalogus product inside one Brick.

    Preference order keeps known household evidence first, but deliberately
    permits another exact Catalogus product in the same Brick when retailer
    article numbers differ. This makes the result a representative household
    photo rather than a claim that every purchase had the same GTIN.
    """
    row = conn.execute(
        text(
            """
            SELECT
                gp.id AS global_product_id,
                gp.image_url,
                CASE
                    WHEN gp.id = :direct_global_product_id THEN 0
                    WHEN EXISTS (
                        SELECT 1
                        FROM product_identities identity_row
                        WHERE identity_row.household_article_id = :household_article_id
                          AND identity_row.global_product_id = gp.id
                    ) THEN 1
                    WHEN EXISTS (
                        SELECT 1
                        FROM purchase_import_lines purchase_line
                        WHERE purchase_line.matched_household_article_id = :household_article_id
                          AND purchase_line.matched_global_product_id = gp.id
                    ) THEN 2
                    ELSE 3
                END AS source_rank
            FROM global_products gp
            JOIN global_product_gpc_bricks assignment
              ON assignment.global_product_id = gp.id
            WHERE assignment.brick_code = :brick_code
              AND lower(COALESCE(gp.status, 'active')) = 'active'
              AND trim(COALESCE(gp.primary_gtin, '')) <> ''
              AND trim(COALESCE(gp.image_url, '')) <> ''
            ORDER BY
                source_rank ASC,
                CASE WHEN gp.updated_at IS NULL THEN 1 ELSE 0 END ASC,
                gp.updated_at DESC,
                gp.id ASC
            LIMIT 1
            """
        ),
        {
            "household_article_id": household_article_id,
            "direct_global_product_id": direct_global_product_id,
            "brick_code": brick_code,
        },
    ).mappings().first()
    if not row:
        return None
    result = dict(row)
    rank = int(result.get("source_rank") or 0)
    result["selection_source"] = {
        0: "direct_exact_product",
        1: "household_product_identity",
        2: "purchase_history",
        3: "same_gpc_brick_catalog",
    }.get(rank, "same_gpc_brick_catalog")
    return result


def ensure_representative_product_for_household_article(
    conn,
    household_article_id: str,
    *,
    article: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist or repair one representative exact product for a household article."""
    article_id = _normalized(household_article_id)
    if not article_id:
        return {"status": "unresolved", "household_article_id": ""}

    resolved_article = dict(article or {})
    if _normalized(resolved_article.get("id")) != article_id:
        resolved_article = _article_row(conn, article_id) or {}
    if not resolved_article:
        return {"status": "unresolved", "household_article_id": article_id}

    anchor_brick = _anchor_brick_code(conn, resolved_article)
    existing = _representative_row(conn, article_id)
    if _valid_representative(existing, anchor_brick):
        return {
            "status": "kept",
            "household_article_id": article_id,
            "global_product_id": _normalized(existing.get("global_product_id")),
            "brick_code": anchor_brick,
            "image_url": _normalized(existing.get("image_url")),
            "selection_source": _normalized(existing.get("selection_source")),
        }

    direct_product_id = _normalized(resolved_article.get("global_product_id"))
    candidate = (
        _candidate_product(
            conn,
            household_article_id=article_id,
            direct_global_product_id=direct_product_id,
            brick_code=anchor_brick,
        )
        if anchor_brick
        else None
    )
    if not candidate:
        if existing:
            conn.execute(
                text(
                    f"DELETE FROM {REPRESENTATIVE_TABLE} "
                    "WHERE household_article_id = :household_article_id"
                ),
                {"household_article_id": article_id},
            )
            return {
                "status": "cleared",
                "household_article_id": article_id,
                "brick_code": anchor_brick,
            }
        return {
            "status": "unresolved",
            "household_article_id": article_id,
            "brick_code": anchor_brick,
        }

    global_product_id = _normalized(candidate.get("global_product_id"))
    selection_source = _normalized(candidate.get("selection_source")) or "same_gpc_brick_catalog"
    conn.execute(
        text(
            f"""
            INSERT INTO {REPRESENTATIVE_TABLE} (
                household_article_id,
                global_product_id,
                brick_code,
                selection_source,
                created_at,
                updated_at
            ) VALUES (
                :household_article_id,
                :global_product_id,
                :brick_code,
                :selection_source,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT(household_article_id) DO UPDATE SET
                global_product_id = excluded.global_product_id,
                brick_code = excluded.brick_code,
                selection_source = excluded.selection_source,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "household_article_id": article_id,
            "global_product_id": global_product_id,
            "brick_code": anchor_brick,
            "selection_source": selection_source,
        },
    )
    return {
        "status": "selected" if not existing else "repaired",
        "household_article_id": article_id,
        "global_product_id": global_product_id,
        "brick_code": anchor_brick,
        "image_url": _normalized(candidate.get("image_url")),
        "selection_source": selection_source,
    }


def backfill_household_article_representative_products(conn) -> dict[str, int]:
    """Idempotently backfill existing household articles after schema migration."""
    rows = [
        dict(row)
        for row in conn.execute(
            text(
                """
                SELECT id, household_id, global_product_id, barcode
                FROM household_articles
                ORDER BY household_id, id
                """
            )
        ).mappings().all()
    ]
    counts = {
        "scanned": len(rows),
        "selected": 0,
        "repaired": 0,
        "kept": 0,
        "cleared": 0,
        "unresolved": 0,
    }
    for article in rows:
        result = ensure_representative_product_for_household_article(
            conn,
            _normalized(article.get("id")),
            article=article,
        )
        status = _normalized(result.get("status"))
        if status in counts:
            counts[status] += 1
        else:
            counts["unresolved"] += 1
    return counts


def representative_image_urls_for_household_articles(
    conn,
    article_rows: Iterable[dict[str, Any]],
) -> dict[str, str]:
    """Read representative images without mutating the request path."""
    result: dict[str, str] = {}
    for raw_article in article_rows:
        article = dict(raw_article or {})
        article_id = _normalized(article.get("id"))
        if not article_id:
            continue
        anchor_brick = _anchor_brick_code(conn, article)
        if not anchor_brick:
            continue

        existing = _representative_row(conn, article_id)
        if _valid_representative(existing, anchor_brick):
            result[article_id] = _normalized(existing.get("image_url"))
            continue

        candidate = _candidate_product(
            conn,
            household_article_id=article_id,
            direct_global_product_id=_normalized(article.get("global_product_id")),
            brick_code=anchor_brick,
        )
        image_url = _normalized((candidate or {}).get("image_url"))
        if image_url:
            result[article_id] = image_url
    return result
