from __future__ import annotations

import base64
import binascii
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import inspect, text

from app.api.catalog_gpc_routes import router as catalog_gpc_router
from app.db import engine
from app.services.session_request_context import (
    require_platform_permission_from_session,
    resolve_current_server_session,
)


router = APIRouter(prefix="/api/catalog", tags=["catalog"])
router.include_router(catalog_gpc_router)

CATALOG_IMAGE_UPDATE_PERMISSION = "platform.catalog.update"
CATALOG_IMAGE_MAX_BYTES = 350_000
CATALOG_IMAGE_DATA_URL_PATTERN = re.compile(
    r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\r\n]+)$",
    re.IGNORECASE,
)


class CatalogImageUpdateRequest(BaseModel):
    image_data_url: str

    @field_validator("image_data_url")
    @classmethod
    def validate_image_data_url_present(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Foto ontbreekt")
        return normalized


class CatalogBulkDeleteRequest(BaseModel):
    global_product_ids: list[str]

    @field_validator("global_product_ids")
    @classmethod
    def validate_global_product_ids(cls, value: list[str]) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("global_product_ids moet een lijst zijn")
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_id in value:
            product_id = str(raw_id or "").strip()
            if not product_id or product_id in seen:
                continue
            seen.add(product_id)
            normalized.append(product_id)
        if not normalized:
            raise ValueError("Selecteer minimaal één catalogusartikel")
        if len(normalized) > 200:
            raise ValueError("Maximaal 200 catalogusartikelen per bulkactie")
        return normalized


def _require_catalog_delete_superuser() -> None:
    context = resolve_current_server_session()
    if not bool(context.is_platform_superuser):
        raise HTTPException(
            status_code=403,
            detail="Alleen de superuser mag catalogusartikelen verwijderen",
        )


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
        "image_url": "gp.image_url",
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
    source_expression = "COALESCE(gp.source, '')" if "source" in gp_columns else "''"
    primary_gtin_expression = (
        "COALESCE(gp.primary_gtin, '')"
        if "primary_gtin" in gp_columns
        else "''"
    )
    catalog_kind_expression = (
        f"CASE WHEN TRIM({primary_gtin_expression}) = '' "
        "THEN 'generic' ELSE 'exact' END"
    )
    select_parts.append(f"{catalog_kind_expression} AS catalog_kind")

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
    external_links_available = "external_article_product_links" in tables
    alias_source_condition = (
        "LOWER(COALESCE(gp.source, '')) IN "
        "('user', 'receipt_user_confirmed', 'receipt', 'manual')"
        if "source" in gp_columns
        else "FALSE"
    )
    alias_gtin_condition = (
        "COALESCE(TRIM(gp.primary_gtin), '') = ''"
        if "primary_gtin" in gp_columns
        else "TRUE"
    )
    alias_visibility_expression = "TRUE"
    if "status" in gp_columns:
        alias_visibility_expression = (
            "LOWER(TRIM(COALESCE(gp.status, 'active'))) <> 'deleted'"
        )

    if external_links_available:
        joins.append("""
            LEFT JOIN (
                SELECT
                    receipt_text_normalized,
                    MIN(global_product_id) AS target_global_product_id
                FROM external_article_product_links
                WHERE status = 'confirmed'
                  AND COALESCE(receipt_text_normalized, '') <> ''
                GROUP BY receipt_text_normalized
                HAVING COUNT(DISTINCT global_product_id) = 1
            ) catalog_alias_target
              ON catalog_alias_target.receipt_text_normalized =
                 LOWER(TRIM(COALESCE(gp.name, '')))
             AND catalog_alias_target.target_global_product_id <> gp.id
        """)
        alias_visibility_expression = (
            f"({alias_visibility_expression}) AND NOT ("
            f"{alias_source_condition} "
            f"AND {alias_gtin_condition} "
            "AND catalog_alias_target.target_global_product_id IS NOT NULL"
            ")"
        )

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

        if external_links_available:
            legacy_source_condition = (
                "LOWER(COALESCE(legacy_gp.source, '')) IN "
                "('user', 'receipt_user_confirmed', 'receipt', 'manual')"
                if "source" in gp_columns
                else "FALSE"
            )
            legacy_gtin_condition = (
                "COALESCE(TRIM(legacy_gp.primary_gtin), '') = ''"
                if "primary_gtin" in gp_columns
                else "TRUE"
            )
            joins.append(f"""
                LEFT JOIN (
                    SELECT
                        unique_links.target_global_product_id AS global_product_id,
                        COUNT(*) AS redirected_household_article_count
                    FROM {household_table} redirected_ha
                    JOIN global_products legacy_gp
                      ON legacy_gp.id = redirected_ha.global_product_id
                    JOIN (
                        SELECT
                            receipt_text_normalized,
                            MIN(global_product_id) AS target_global_product_id
                        FROM external_article_product_links
                        WHERE status = 'confirmed'
                          AND COALESCE(receipt_text_normalized, '') <> ''
                        GROUP BY receipt_text_normalized
                        HAVING COUNT(DISTINCT global_product_id) = 1
                    ) unique_links
                      ON unique_links.receipt_text_normalized =
                         LOWER(TRIM(COALESCE(legacy_gp.name, '')))
                     AND unique_links.target_global_product_id <> legacy_gp.id
                    WHERE redirected_ha.global_product_id IS NOT NULL
                      AND {legacy_source_condition}
                      AND {legacy_gtin_condition}
                    GROUP BY unique_links.target_global_product_id
                ) redirected_household_counts
                  ON redirected_household_counts.global_product_id = gp.id
            """)
            household_count_expression = (
                "COALESCE(household_counts.household_article_count, 0) + "
                "COALESCE(redirected_household_counts.redirected_household_article_count, 0)"
            )
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
        "primary_gtin": primary_gtin_expression,
        "catalog_kind": catalog_kind_expression,
        "product_type": f"COALESCE({product_type_expression}, '')",
        "source": source_expression,
        "household_article_count": household_count_expression,
        "catalog_visible": alias_visibility_expression,
    }
    return select_parts, joins, expressions


def _catalog_where(
    expressions: dict[str, str],
    name: str,
    brand: str,
    primary_gtin: str,
    catalog_kind: str,
    product_type: str,
    source: str,
    household_article_count: str,
) -> tuple[str, dict[str, Any]]:
    conditions: list[str] = [f"({expressions['catalog_visible']})"]
    params: dict[str, Any] = {}
    filters = {
        "name": name,
        "brand": brand,
        "primary_gtin": primary_gtin,
        "catalog_kind": catalog_kind,
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
    status_condition = (
        "AND LOWER(TRIM(COALESCE(gp.status, 'active'))) <> 'deleted'"
        if "status" in _columns("global_products")
        else ""
    )
    sql = f"""
        SELECT {", ".join(select_parts)}
        FROM global_products gp
        {" ".join(joins)}
        WHERE gp.id = :global_product_id
          {status_condition}
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
    catalog_kind: str = Query(default="", max_length=50),
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
        catalog_kind,
        product_type,
        source,
        household_article_count,
    )
    order_expression = expressions.get(sort_by, expressions["name"])
    direction = "DESC" if sort_direction.lower() == "desc" else "ASC"
    if sort_by in {"name", "catalog_kind", "brand", "primary_gtin", "product_type", "source"}:
        order_sql = (
            f"LOWER({order_expression}) {direction}, "
            f"{order_expression} {direction}"
        )
    else:
        order_sql = f"{order_expression} {direction}"
    from_sql = f"FROM global_products gp {' '.join(joins)} {where_sql}"

    count_sql = f"SELECT COUNT(*) {from_sql}"
    page_sql = f"""
        SELECT {", ".join(select_parts)}
        {from_sql}
        ORDER BY {order_sql}, gp.id ASC
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



def _validated_catalog_image_data_url(value: str) -> str:
    normalized = str(value or "").strip()
    match = CATALOG_IMAGE_DATA_URL_PATTERN.fullmatch(normalized)
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Foto moet een JPEG-, PNG- of WebP-afbeelding zijn",
        )
    mime_type = match.group(1).lower()
    payload = "".join(match.group(2).split())
    try:
        binary = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Foto bevat ongeldige afbeeldingsdata") from exc
    if not binary:
        raise HTTPException(status_code=400, detail="Foto bevat geen afbeeldingsdata")
    if len(binary) > CATALOG_IMAGE_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Foto is na compressie nog te groot",
        )

    valid_magic = (
        mime_type == "image/jpeg" and binary.startswith(b"\xff\xd8\xff")
    ) or (
        mime_type == "image/png" and binary.startswith(b"\x89PNG\r\n\x1a\n")
    ) or (
        mime_type == "image/webp"
        and len(binary) >= 12
        and binary[:4] == b"RIFF"
        and binary[8:12] == b"WEBP"
    )
    if not valid_magic:
        raise HTTPException(
            status_code=400,
            detail="Bestandsinhoud komt niet overeen met het afbeeldingstype",
        )
    return f"data:{mime_type};base64,{base64.b64encode(binary).decode('ascii')}"


@router.put("/{global_product_id}/image")
def update_catalog_product_image(
    global_product_id: str,
    payload: CatalogImageUpdateRequest,
):
    require_platform_permission_from_session(CATALOG_IMAGE_UPDATE_PERMISSION)
    if "global_products" not in _tables():
        raise HTTPException(status_code=404, detail="Catalogus is niet beschikbaar")
    product_columns = _columns("global_products")
    if "image_url" not in product_columns:
        raise HTTPException(
            status_code=503,
            detail="Catalogus ondersteunt productfoto's nog niet",
        )

    image_data_url = _validated_catalog_image_data_url(payload.image_data_url)
    updated_at_sql = ", updated_at = CURRENT_TIMESTAMP" if "updated_at" in product_columns else ""

    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT id, status
                FROM global_products
                WHERE id = :global_product_id
                LIMIT 1
            """),
            {"global_product_id": global_product_id},
        ).mappings().first()
        if not row or str(row.get("status") or "").strip().lower() == "deleted":
            raise HTTPException(status_code=404, detail="Universeel artikel niet gevonden")

        conn.execute(
            text(f"""
                UPDATE global_products
                SET image_url = :image_data_url{updated_at_sql}
                WHERE id = :global_product_id
            """),
            {
                "global_product_id": global_product_id,
                "image_data_url": image_data_url,
            },
        )

    return {
        "global_product_id": global_product_id,
        "image_url": image_data_url,
    }


@router.post("/bulk-delete")
def bulk_delete_catalog_products(payload: CatalogBulkDeleteRequest):
    _require_catalog_delete_superuser()
    if "global_products" not in _tables():
        raise HTTPException(status_code=404, detail="Catalogus is niet beschikbaar")
    product_columns = _columns("global_products")
    if "status" not in product_columns:
        raise HTTPException(
            status_code=503,
            detail="Catalogus ondersteunt verwijderen nog niet",
        )

    deleted_ids: list[str] = []
    already_deleted_ids: list[str] = []
    not_found_ids: list[str] = []
    updated_at_sql = ", updated_at = CURRENT_TIMESTAMP" if "updated_at" in product_columns else ""

    with engine.begin() as conn:
        for product_id in payload.global_product_ids:
            row = conn.execute(
                text("""
                    SELECT id, status
                    FROM global_products
                    WHERE id = :global_product_id
                    LIMIT 1
                """),
                {"global_product_id": product_id},
            ).mappings().first()
            if not row:
                not_found_ids.append(product_id)
                continue
            if str(row.get("status") or "").strip().lower() == "deleted":
                already_deleted_ids.append(product_id)
                continue
            conn.execute(
                text(f"""
                    UPDATE global_products
                    SET status = 'deleted'{updated_at_sql}
                    WHERE id = :global_product_id
                """),
                {"global_product_id": product_id},
            )
            deleted_ids.append(product_id)

    return {
        "deleted_count": len(deleted_ids),
        "deleted_ids": deleted_ids,
        "already_deleted_ids": already_deleted_ids,
        "not_found_ids": not_found_ids,
    }


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
