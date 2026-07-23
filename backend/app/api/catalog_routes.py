from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import inspect, text

from app.db import engine

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def _tables() -> set[str]:
    return set(inspect(engine).get_table_names())


def _columns(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {str(column.get("name") or "") for column in inspect(engine).get_columns(table_name)}


def _quality_status(row: dict[str, Any]) -> str:
    if not str(row.get("primary_gtin") or "").strip():
        return "Controle nodig"
    if not str(row.get("product_type") or "").strip():
        return "Controle nodig"
    return "Compleet"


def _household_table() -> str | None:
    tables = _tables()
    for candidate in ("household_articles", "household_products"):
        if candidate in tables and "global_product_id" in _columns(candidate):
            return candidate
    return None


def _catalog_base_rows() -> list[dict[str, Any]]:
    tables = _tables()
    if "global_products" not in tables:
        return []

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
        f"{expression} AS {alias}" if alias in gp_columns else f"NULL AS {alias}"
        for alias, expression in selectable.items()
    ]

    joins: list[str] = []
    if {"product_group_memberships", "product_inventory_groups"}.issubset(tables):
        joins.extend(
            [
                """
                LEFT JOIN product_group_memberships pgm
                  ON pgm.global_product_id = gp.id
                 AND COALESCE(pgm.active, 1) = 1
                """,
                """
                LEFT JOIN product_inventory_groups pig
                  ON pig.inventory_group_key = pgm.inventory_group_key
                 AND COALESCE(pig.active, 1) = 1
                """,
            ]
        )
        select_parts.extend(
            [
                "pgm.inventory_group_key AS product_type_id",
                "pig.display_name AS product_type",
            ]
        )
    else:
        select_parts.extend(["NULL AS product_type_id", "NULL AS product_type"])

    household_table = _household_table()
    if household_table:
        joins.append(
            f"""
            LEFT JOIN (
                SELECT global_product_id, COUNT(*) AS household_article_count
                FROM {household_table}
                WHERE global_product_id IS NOT NULL
                GROUP BY global_product_id
            ) hac ON hac.global_product_id = gp.id
            """
        )
        select_parts.append("COALESCE(hac.household_article_count, 0) AS household_article_count")
    else:
        select_parts.append("0 AS household_article_count")

    if "product_identities" in tables and "global_product_id" in _columns("product_identities"):
        joins.append(
            """
            LEFT JOIN (
                SELECT global_product_id, COUNT(*) AS identity_count
                FROM product_identities
                GROUP BY global_product_id
            ) pic ON pic.global_product_id = gp.id
            """
        )
        select_parts.append("COALESCE(pic.identity_count, 0) AS identity_count")
    else:
        select_parts.append("0 AS identity_count")

    query = f"""
        SELECT {", ".join(select_parts)}
        FROM global_products gp
        {" ".join(joins)}
        ORDER BY COALESCE(gp.name, ''), gp.id
    """

    with engine.begin() as conn:
        rows = [dict(row) for row in conn.execute(text(query)).mappings().all()]

    for row in rows:
        row["quality_status"] = _quality_status(row)
    return rows


@router.get("")
def list_catalog(
    query: str = Query(default="", max_length=200),
    product_type: str = Query(default="", max_length=200),
    quality_status: str = Query(default="", max_length=50),
    limit: int = Query(default=500, ge=1, le=2000),
):
    rows = _catalog_base_rows()
    query_value = query.strip().lower()
    product_type_value = product_type.strip().lower()
    quality_value = quality_status.strip().lower()

    if query_value:
        rows = [
            row
            for row in rows
            if query_value
            in " ".join(
                [
                    str(row.get("name") or ""),
                    str(row.get("brand") or ""),
                    str(row.get("primary_gtin") or ""),
                    str(row.get("product_type") or ""),
                ]
            ).lower()
        ]
    if product_type_value:
        rows = [
            row
            for row in rows
            if product_type_value in str(row.get("product_type") or "").lower()
        ]
    if quality_value:
        rows = [
            row
            for row in rows
            if quality_value == str(row.get("quality_status") or "").lower()
        ]

    return {"items": rows[:limit], "total": len(rows)}


@router.get("/{global_product_id}")
def get_catalog_product(global_product_id: str):
    rows = _catalog_base_rows()
    product = next(
        (row for row in rows if str(row.get("id") or "") == str(global_product_id)),
        None,
    )
    if not product:
        raise HTTPException(status_code=404, detail="Universeel artikel niet gevonden")

    tables = _tables()
    identities: list[dict[str, Any]] = []
    if "product_identities" in tables and "global_product_id" in _columns("product_identities"):
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
            identities = [
                dict(row)
                for row in conn.execute(
                    text(
                        f"""
                        SELECT {", ".join(select_parts)}
                        FROM product_identities
                        WHERE global_product_id = :global_product_id
                        ORDER BY COALESCE(is_primary, 0) DESC, identity_type, identity_value
                        """
                    ),
                    {"global_product_id": global_product_id},
                ).mappings().all()
            ]

    household_articles: list[dict[str, Any]] = []
    household_table = _household_table()
    if household_table:
        table_columns = _columns(household_table)
        requested = [
            "id",
            "household_id",
            "name",
            "article_name",
            "minimum_stock",
            "ideal_stock",
            "article_group_id",
        ]
        select_parts = [
            column if column in table_columns else f"NULL AS {column}"
            for column in requested
        ]
        with engine.begin() as conn:
            household_articles = [
                dict(row)
                for row in conn.execute(
                    text(
                        f"""
                        SELECT {", ".join(select_parts)}
                        FROM {household_table}
                        WHERE global_product_id = :global_product_id
                        ORDER BY household_id, id
                        """
                    ),
                    {"global_product_id": global_product_id},
                ).mappings().all()
            ]

    return {
        "product": product,
        "identities": identities,
        "household_articles": household_articles,
    }
