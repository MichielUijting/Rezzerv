from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import inspect, text

from app.api.catalog_gpc_routes import router as catalog_gpc_router
from app.db import engine


router = APIRouter(prefix="/api/catalog", tags=["catalog"])
router.include_router(catalog_gpc_router)


def _tables() -> set[str]:
    return set(inspect(engine).get_table_names())


def _columns(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {
        str(column.get("name") or "")
        for column in inspect(engine).get_columns(table_name)
    }


def _household_table() -> str | None:
    tables = _tables()
    for candidate in ("household_articles", "household_products"):
        if candidate in tables and "global_product_id" in _columns(candidate):
            return candidate
    return None


def _catalog_projection() -> tuple[list[str], list[str], dict[str, str]]:
    tables = _tables()
    gp_columns = _columns("global_products")
    selectable = {
        "id": "gp.id",
        "name": "gp.name",
        "brand": "gp.brand",
        "primary_gtin": "gp.primary_gtin",
        "source": "gp.source",
        "status": "gp.status",
        "created_at": "gp.created_at",
        "updated_at": "gp.updated_at",
    }
    select_parts = [
        f"{expression} AS {alias}"
        if alias in gp_columns
        else f"NULL AS {alias}"
        for alias, expression in selectable.items()
    ]
    joins: list[str] = []

    legacy_product_type = "NULL"
    legacy_product_type_id = "NULL"
    if {"product_group_memberships", "product_inventory_groups"}.issubset(tables):
        joins.append("""
            LEFT JOIN (
                SELECT pgm.global_product_id,
                       MAX(pgm.inventory_group_key) AS inventory_group_key,
                       MAX(pig.display_name) AS display_name
                FROM product_group_memberships pgm
                JOIN product_inventory_groups pig
                  ON pig.inventory_group_key = pgm.inventory_group_key
                WHERE COALESCE(pgm.active, 1) = 1
                  AND COALESCE(pig.active, 1) = 1
                GROUP BY pgm.global_product_id
            ) legacy_group ON legacy_group.global_product_id = gp.id
        """)
        legacy_product_type = "legacy_group.display_name"
        legacy_product_type_id = "legacy_group.inventory_group_key"

    gpc_product_type = "NULL"
    gpc_brick_code = "NULL"
    if {"global_product_gpc_bricks", "gpc_bricks"}.issubset(tables):
        joins.extend([
            """
            LEFT JOIN global_product_gpc_bricks catalog_gpc
              ON catalog_gpc.global_product_id = gp.id
            """,
            """
            LEFT JOIN gpc_bricks catalog_brick
              ON catalog_brick.brick_code = catalog_gpc.brick_code
            """,
        ])
        gpc_brick_code = "catalog_gpc.brick_code"
        if "gpc_translations" in tables:
            gpc_product_type = """
                COALESCE(
                    (SELECT tr.translated_text
                     FROM gpc_translations tr
                     WHERE tr.entity_type = 'brick'
                       AND tr.entity_code = catalog_gpc.brick_code
                       AND tr.language_code = 'nl'
                     LIMIT 1),
                    catalog_brick.description
                )
            """
        else:
            gpc_product_type = "catalog_brick.description"

    product_type_expression = f"COALESCE({gpc_product_type}, {legacy_product_type})"
    product_type_id_expression = f"COALESCE({gpc_brick_code}, {legacy_product_type_id})"
    select_parts.extend([
        f"{product_type_id_expression} AS product_type_id",
        f"{product_type_expression} AS product_type",
        f"{gpc_brick_code} AS gpc_brick_code",
    ])

    household_table = _household_table()
    if household_table:
        joins.append(f"""
            LEFT JOIN (
                SELECT global_product_id, COUNT(*) AS household_article_count
                FROM {household_table}
                WHERE global_product_id IS NOT NULL
                GROUP BY global_product_id
            ) household_counts ON household_counts.global_product_id = gp.id
        """)
        household_count_expression = "COALESCE(household_counts.household_article_count, 0)"
    else:
        household_count_expression = "0"
    select_parts.append(f"{household_count_expression} AS household_article_count")

    if "product_identities" in tables and "global_product_id" in _columns("product_identities"):
        joins.append("""
            LEFT JOIN (
                SELECT global_product_id, COUNT(*) AS identity_count
                FROM product_identities
                GROUP BY global_product_id
            ) identity_counts ON identity_counts.global_product_id = gp.id
        """)
        identity_count_expression = "COALESCE(identity_counts.identity_count, 0)"
    else:
        identity_count_expression = "0"
    select_parts.append(f"{identity_count_expression} AS identity_count")

    expressions = {
        "name": "COALESCE(gp.name, '')",
        "brand": "COALESCE(gp.brand, '')",
        "primary_gtin": "COALESCE(gp.primary_gtin, '')",
        "product_type": f"COALESCE({product_type_expression}, '')",
        "source": "COALESCE(gp.source, '')",
        "household_article_count": household_count_expression,
    }
    return select_parts, joins, expressions


def _catalog_where(
    expressions: dict[str, str],
    name: str,
    brand: str,
    primary_gtin: str,
    product_type: str,
    source: str,
    household_article_count: str,
) -> tuple[str, dict[str, Any]]:
    conditions: list[str] = []
    params: dict[str, Any] = {}
    filters = {
        "name": name,
        "brand": brand,
        "primary_gtin": primary_gtin,
        "product_type": product_type,
        "source": source,
    }
    for key, raw_value in filters.items():
        value = raw_value.strip().lower()
        if value:
            conditions.append(f"LOWER({expressions[key]}) LIKE :{key}")
            params[key] = f"%{value}%"
    household_value = household_article_count.strip()
    if household_value:
        conditions.append(
            f"CAST({expressions['household_article_count']} AS TEXT) LIKE :household_article_count"
        )
        params["household_article_count"] = f"%{household_value}%"
    return ("WHERE " + " AND ".join(conditions)) if conditions else "", params


def _catalog_row(global_product_id: str) -> dict[str, Any] | None:
    if "global_products" not in _tables():
        return None
    select_parts, joins, _ = _catalog_projection()
    sql = f"""
        SELECT {", ".join(select_parts)}
        FROM global_products gp
        {" ".join(joins)}
        WHERE gp.id = :global_product_id
        LIMIT 1
    """
    with engine.begin() as conn:
        row = conn.execute(
            text(sql),
            {"global_product_id": global_product_id},
        ).mappings().first()
    return dict(row) if row else None


@router.get("")
def list_catalog(
    name: str = Query(default="", max_length=200),
    brand: str = Query(default="", max_length=200),
    primary_gtin: str = Query(default="", max_length=200),
    product_type: str = Query(default="", max_length=200),
    source: str = Query(default="", max_length=200),
    household_article_count: str = Query(default="", max_length=50),
    sort_by: str = Query(default="name", max_length=50),
    sort_direction: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=10, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    if "global_products" not in _tables():
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    select_parts, joins, expressions = _catalog_projection()
    where_sql, params = _catalog_where(
        expressions,
        name,
        brand,
        primary_gtin,
        product_type,
        source,
        household_article_count,
    )
    order_expression = expressions.get(sort_by, expressions["name"])
    direction = "DESC" if sort_direction.lower() == "desc" else "ASC"
    from_sql = f"FROM global_products gp {' '.join(joins)} {where_sql}"

    count_sql = f"SELECT COUNT(*) {from_sql}"
    page_sql = f"""
        SELECT {", ".join(select_parts)}
        {from_sql}
        ORDER BY LOWER({order_expression}) {direction}, {order_expression} {direction}, gp.id ASC
        LIMIT :limit OFFSET :offset
    """
    page_params = {**params, "limit": limit, "offset": offset}
    with engine.begin() as conn:
        total = int(conn.execute(text(count_sql), params).scalar() or 0)
        items = [
            dict(row)
            for row in conn.execute(text(page_sql), page_params).mappings().all()
        ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _identity_rows(global_product_id: str) -> list[dict[str, Any]]:
    if (
        "product_identities" not in _tables()
        or "global_product_id" not in _columns("product_identities")
    ):
        return []
    identity_columns = _columns("product_identities")
    requested = [
        "id",
        "identity_type",
        "identity_value",
        "is_primary",
        "source",
        "created_at",
    ]
    select_parts = [
        column if column in identity_columns else f"NULL AS {column}"
        for column in requested
    ]
    with engine.begin() as conn:
        return [
            dict(row)
            for row in conn.execute(text(f"""
                SELECT {", ".join(select_parts)}
                FROM product_identities
                WHERE global_product_id = :global_product_id
                ORDER BY COALESCE(is_primary, FALSE) DESC,
                         identity_type,
                         identity_value
            """), {
                "global_product_id": global_product_id,
            }).mappings().all()
        ]


def _household_article_rows(global_product_id: str) -> list[dict[str, Any]]:
    household_table = _household_table()
    if not household_table:
        return []
    columns = _columns(household_table)
    name_expression = (
        "COALESCE(custom_name, naam) AS name"
        if {"custom_name", "naam"}.issubset(columns)
        else "naam AS name"
        if "naam" in columns
        else "name"
        if "name" in columns
        else "NULL AS name"
    )
    article_name_expression = (
        "naam AS article_name"
        if "naam" in columns
        else "article_name"
        if "article_name" in columns
        else "NULL AS article_name"
    )
    minimum_expression = (
        "min_stock AS minimum_stock"
        if "min_stock" in columns
        else "minimum_stock"
        if "minimum_stock" in columns
        else "NULL AS minimum_stock"
    )
    ideal_expression = "ideal_stock" if "ideal_stock" in columns else "NULL AS ideal_stock"
    group_expression = "article_group_id" if "article_group_id" in columns else "NULL AS article_group_id"
    with engine.begin() as conn:
        return [
            dict(row)
            for row in conn.execute(text(f"""
                SELECT id,
                       household_id,
                       {name_expression},
                       {article_name_expression},
                       {minimum_expression},
                       {ideal_expression},
                       {group_expression}
                FROM {household_table}
                WHERE global_product_id = :global_product_id
                ORDER BY household_id, id
            """), {
                "global_product_id": global_product_id,
            }).mappings().all()
        ]


def _receipt_line_rows(global_product_id: str) -> list[dict[str, Any]]:
    if not {"purchase_import_lines", "purchase_import_batches"}.issubset(_tables()):
        return []
    with engine.begin() as conn:
        return [
            dict(row)
            for row in conn.execute(text("""
                SELECT
                    pil.id,
                    pil.batch_id,
                    pil.article_name_raw,
                    pil.matched_household_article_id,
                    COALESCE(pil.matched_global_product_id, ha.global_product_id) AS matched_global_product_id,
                    COALESCE(ha.custom_name, ha.naam) AS household_article_name,
                    COALESCE(ha.barcode, gp.primary_gtin) AS gtin,
                    pib.created_at
                FROM purchase_import_lines pil
                JOIN purchase_import_batches pib ON pib.id = pil.batch_id
                LEFT JOIN household_articles ha ON ha.id = pil.matched_household_article_id
                LEFT JOIN global_products gp
                  ON gp.id = COALESCE(pil.matched_global_product_id, ha.global_product_id)
                WHERE COALESCE(pil.matched_global_product_id, ha.global_product_id) = :global_product_id
                ORDER BY pib.created_at DESC, pil.id DESC
            """), {
                "global_product_id": global_product_id,
            }).mappings().all()
        ]


@router.get("/{global_product_id}")
def get_catalog_product(global_product_id: str):
    product = _catalog_row(global_product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Universeel artikel niet gevonden")
    return {
        "product": product,
        "identities": _identity_rows(global_product_id),
        "household_articles": _household_article_rows(global_product_id),
        "receipt_lines": _receipt_line_rows(global_product_id),
    }
