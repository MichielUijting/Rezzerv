from __future__ import annotations

import base64
import binascii
import logging
from time import perf_counter
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import inspect, text

from app.api.catalog_gpc_routes import router as catalog_gpc_router
from app.api.catalog_shopify_review_routes import router as shopify_review_router
from app.db import engine
from app.services.barcode_identity_service import validate_barcode
from app.services.ed2_confirmed_barcode_service import materialize_saved_ed2_barcode
from app.services.ed2_receipt_family_link_service import (
    family_options, confirm_courgette_receipt,
)
from app.services.curated_identity_batch_service import (
    matching_batch_preview, confirm_matching_batch,
)
from app.services.ed2_barcode_correction_service import (
    preview_lidl_barcode_correction, confirm_lidl_barcode_correction,
)
from app.services.global_product_service import build_global_product_fingerprint
from app.services.article_synonym_service import RETAILER_NAMES
from app.services.external_article_confirmation_service import resolve_external_article_identity
from app.services.external_article_product_link_service import (
    normalize_external_link_retailer_code,
    normalize_external_link_article_code,
    normalize_external_link_receipt_text,
)
from app.services.off_search_service import OffSearchError, OffUnavailableError, search_off_candidates
from app.services.off_manual_catalog_link_service import confirm_selected_off_catalog_product
from app.services.off_manual_search_proof import issue_manual_off_proof
from app.services.dutch_gpc_projection_service import ensure_dutch_gpc_assignments
from app.services.session_request_context import (
    require_household_admin_from_session,
    require_platform_permission_from_session,
    resolve_current_server_session,
)


router = APIRouter(prefix="/api/catalog", tags=["catalog"])
router.include_router(catalog_gpc_router)
router.include_router(shopify_review_router)

CATALOG_IMAGE_UPDATE_PERMISSION = "platform.catalog.update"
CATALOG_IMAGE_MAX_BYTES = 350_000
CATALOG_IMAGE_DATA_URL_PATTERN = re.compile(
    r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\r\n]+)$",
    re.IGNORECASE,
)


class CatalogNameUpdateRequest(BaseModel):
    name: str
    expected_name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = " ".join(str(value or "").split())
        if not normalized:
            raise ValueError("Vul een artikelnaam in")
        if len(normalized) > 200:
            raise ValueError("De artikelnaam mag maximaal 200 tekens bevatten")
        return normalized

    @field_validator("expected_name")
    @classmethod
    def validate_expected_name(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("De bestaande artikelnaam ontbreekt")
        return normalized


class CatalogGtinUpdateRequest(BaseModel):
    gtin: str


class Ed2ManualBarcodeRequest(BaseModel):
    receipt_item_id: str
    gtin: str
    allow_off_mismatch: bool = False
    # Exclusive to Superuser barcode import: attach the full OFF product after explicit review.
    import_off_product_override: bool = False


class Ed2HistoricalBarcodeSelection(BaseModel):
    receipt_item_id: str
    gtin: str


class Ed2HistoricalBarcodesRequest(BaseModel):
    selections: list[Ed2HistoricalBarcodeSelection]

    @field_validator("selections")
    @classmethod
    def validate_selections(cls, value: list[Ed2HistoricalBarcodeSelection]):
        if not 1 <= len(value) <= 50:
            raise ValueError("Selecteer 1 tot en met 50 reeds opgeslagen barcodes.")
        ids = [str(item.receipt_item_id or "").strip() for item in value]
        if any(not item for item in ids) or len(ids) != len(set(ids)):
            raise ValueError("Selecties moeten unieke, bestaande bonartikel-ID's bevatten.")
        return value


class Ed2CuratedMatchingBatchConfirmation(BaseModel):
    target_product_id: str
    receipt_item_ids: list[str]
    fingerprint: str


class Ed2CourgetteFamilyConfirmation(BaseModel):
    receipt_item_id: str
    target_product_id: str
    match_mode: str
    fingerprint: str


class Ed2LidlBarcodeCorrectionPreviewRequest(BaseModel):
    receipt_item_id: str
    new_gtin: str


class Ed2LidlBarcodeCorrectionConfirmRequest(Ed2LidlBarcodeCorrectionPreviewRequest):
    expected_old_gtin: str
    preview_fingerprint: str


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


def _catalog_retailer_code(expression: str) -> str:
    """Match the canonical retailer keys used by article-synonym suggestions."""
    cleaned = (
        f"LOWER(REPLACE(REPLACE(TRIM(COALESCE({expression}, '')), ' ', '-'), '_', '-'))"
    )
    return (
        f"CASE WHEN {cleaned} IN ('albert-heijn', 'albert-heijn-digitaal', " 
        f"'albertheijn') THEN 'ah' " 
        f"WHEN {cleaned} IN ('lidl-nederland-gmbh', 'lidl-nederland') THEN 'lidl' " 
        f"ELSE {cleaned} END"
    )


def _catalog_linked_store_projection(tables: set[str], gp_columns: set[str]) -> tuple[str, str]:
    """Count unique other stores reached by *direct* confirmed synonym links.

    Use the same confirmed (possibly multi-store) evidence as synonym
    suggestions: only disjoint nonempty shop sets establish a cross-store
    relation. Count distinct peer shops, never household or receipt rows.
    """
    if "article_synonym_links" not in tables:
        return "", "0"

    shop_codes = ", ".join(f"'{code}'" for code in sorted(RETAILER_NAMES) if code != "albert-heijn")
    source = _catalog_retailer_code("shop_product.source") if "source" in gp_columns else "''"
    source_fallback = f"CASE WHEN {source} IN ({shop_codes}) THEN {source} ELSE NULL END"
    if "external_article_product_links" in tables:
        external_shop = _catalog_retailer_code("retailer_link.retailer_code")
        external_join = """
            LEFT JOIN external_article_product_links retailer_link
              ON retailer_link.global_product_id = shop_product.id
             AND retailer_link.status = 'confirmed'
        """
        documented_shop = f"NULLIF({external_shop}, '')"
    else:
        external_join = ""
        documented_shop = "NULL::text"

    active = (
        "AND LOWER(TRIM(COALESCE(shop_product.status, 'active'))) <> 'deleted'"
        if "status" in gp_columns else ""
    )
    joins = f"""
        LEFT JOIN (
            WITH synonym_participants AS (
                SELECT left_product_id AS id FROM article_synonym_links
                UNION
                SELECT right_product_id AS id FROM article_synonym_links
            ), documented_retailers AS (
                SELECT shop_product.id,
                       CASE
                         WHEN COUNT(DISTINCT {documented_shop}) > 0
                           THEN ARRAY_REMOVE(ARRAY_AGG(DISTINCT {documented_shop}), NULL)
                         WHEN {source_fallback} IS NOT NULL
                           THEN ARRAY[{source_fallback}]
                         ELSE ARRAY[]::text[]
                       END AS retailer_codes
                FROM synonym_participants participant
                JOIN global_products shop_product ON shop_product.id = participant.id
                {external_join}
                WHERE 1=1 {active}
                GROUP BY shop_product.id, {source}
            ), direct_pairs AS (
                SELECT left_product_id AS product_id, right_product_id AS peer_id
                FROM article_synonym_links
                UNION ALL
                SELECT right_product_id AS product_id, left_product_id AS peer_id
                FROM article_synonym_links
            )
            SELECT direct_pairs.product_id,
                   COUNT(DISTINCT peer_store.retailer_code) AS linked_store_count
            FROM direct_pairs
            JOIN documented_retailers origin ON origin.id = direct_pairs.product_id
            JOIN documented_retailers peer ON peer.id = direct_pairs.peer_id
            JOIN LATERAL UNNEST(peer.retailer_codes) AS peer_store(retailer_code) ON TRUE
            WHERE CARDINALITY(origin.retailer_codes) > 0
              AND NOT (origin.retailer_codes && peer.retailer_codes)
            GROUP BY direct_pairs.product_id
        ) catalog_synonym_stores
          ON catalog_synonym_stores.product_id = gp.id
    """
    return joins, "COALESCE(catalog_synonym_stores.linked_store_count, 0)"


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
    gpc_brick_name = "NULL"
    gpc_class_code = "NULL"
    gpc_class_name = "NULL"
    gpc_family_code = "NULL"
    gpc_family_name = "NULL"
    if {"global_product_gpc_bricks", "gpc_product_groups"}.issubset(tables):
        joins.extend([
            """
            LEFT JOIN global_product_gpc_bricks catalog_gpc
              ON catalog_gpc.global_product_id = gp.id
            """,
            """
            LEFT JOIN gpc_product_groups catalog_gpc_nl
              ON catalog_gpc_nl.gpc_brick_code = catalog_gpc.brick_code
             AND catalog_gpc_nl.language_code = 'nl'
             AND catalog_gpc_nl.active = TRUE
            """,
        ])
        gpc_brick_code = "catalog_gpc.brick_code"
        gpc_brick_name = "catalog_gpc_nl.gpc_brick_name"
        gpc_product_type = gpc_brick_name
        gpc_class_code = "catalog_gpc_nl.gpc_class_code"
        gpc_class_name = "catalog_gpc_nl.gpc_class_name"
        gpc_family_code = "catalog_gpc_nl.gpc_family_code"
        gpc_family_name = "catalog_gpc_nl.gpc_family_name"

    product_type_expression = f"CASE WHEN {gpc_brick_code} IS NOT NULL THEN {gpc_product_type} ELSE {legacy_product_type} END"
    product_type_id_expression = f"COALESCE({gpc_brick_code}, {legacy_product_type_id})"
    select_parts.extend([
        f"{product_type_id_expression} AS product_type_id",
        f"{product_type_expression} AS product_type",
        f"{gpc_brick_code} AS gpc_brick_code",
        f"{gpc_brick_name} AS gpc_brick_name",
        f"{gpc_class_code} AS gpc_class_code",
        f"{gpc_class_name} AS gpc_class_name",
        f"{gpc_family_code} AS gpc_family_code",
        f"{gpc_family_name} AS gpc_family_name",
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

    linked_store_join, linked_store_count = _catalog_linked_store_projection(tables, gp_columns)
    if linked_store_join:
        joins.append(linked_store_join)
    select_parts.append(f"{linked_store_count} AS linked_store_count")

    # Bevestigde artikelclassificaties zijn onafhankelijk van GS1/GPC.
    article_classification = "NULL"
    if "global_product_shopify_classifications" in tables:
        joins.append("""
            LEFT JOIN global_product_shopify_classifications catalog_classification
              ON catalog_classification.global_product_id = gp.id
        """)
        article_classification = (
            "CASE WHEN catalog_classification.is_active THEN "
            "catalog_classification.shopify_path ELSE NULL END"
        )
    # The value shown to users must be the value returned for filtering,
    # sorting and the central Catalogus projection as well.
    visible_article_classification = (
        f"COALESCE({article_classification}, 'Niet geclassificeerd')"
    )
    select_parts.append(f"{visible_article_classification} AS article_classification")

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
        "gpc_brick_code": f"COALESCE({gpc_brick_code}, '')",
        "gpc_brick_name": f"COALESCE({gpc_brick_name}, '')",
        "gpc_class_code": f"COALESCE({gpc_class_code}, '')",
        "gpc_family_code": f"COALESCE({gpc_family_code}, '')",
        "id": "CAST(gp.id AS TEXT)",
        "gpc_class_name": f"COALESCE({gpc_class_name}, '')",
        "gpc_family_name": f"COALESCE({gpc_family_name}, '')",
        "source": source_expression,
        "household_article_count": household_count_expression,
        "linked_store_count": linked_store_count,
        "article_classification": visible_article_classification,
        "catalog_visible": alias_visibility_expression,
    }
    return select_parts, joins, expressions


def _catalog_where(
    expressions: dict[str, str],
    name: str,
    search: str,
    brand: str,
    primary_gtin: str,
    catalog_kind: str,
    product_type: str,
    gpc_brick_code: str,
    gpc_brick_name: str,
    gpc_class: str,
    gpc_family: str,
    source: str,
    household_article_count: str,
    linked_store_count: str,
    article_classification: str,
) -> tuple[str, dict[str, Any]]:
    conditions: list[str] = [f"({expressions['catalog_visible']})"]
    params: dict[str, Any] = {}
    filters = {
        "name": name,
        "brand": brand,
        "primary_gtin": primary_gtin,
        "catalog_kind": catalog_kind,
        "product_type": product_type,
        "gpc_brick_code": gpc_brick_code,
        "gpc_brick_name": gpc_brick_name,
        "gpc_class_name": gpc_class,
        "gpc_family_name": gpc_family,
        "source": source,
        "article_classification": article_classification,
    }
    for key, raw_value in filters.items():
        value = (raw_value if isinstance(raw_value, str) else "").strip().lower()
        if value:
            conditions.append(f"LOWER({expressions[key]}) LIKE :{key}")
            params[key] = f"%{value}%"
    # Free text search across all visible catalog attributes, not just name.
    # Explicit per-column filters above continue to work independently.
    normalized_search = (search if isinstance(search, str) else "").strip().lower()
    if normalized_search:
        searchable_keys = (
            "id", "name", "brand", "primary_gtin", "catalog_kind",
            "product_type", "gpc_brick_code", "gpc_brick_name",
            "gpc_class_code", "gpc_class_name", "gpc_family_code",
            "gpc_family_name", "source", "household_article_count",
            "linked_store_count", "article_classification",
        )
        conditions.append("(" + " OR ".join(
            f"LOWER(CAST({expressions[key]} AS TEXT)) LIKE :search"
            for key in searchable_keys
        ) + ")")
        params["search"] = f"%{normalized_search}%"
    household_value = (
        household_article_count if isinstance(household_article_count, str) else ""
    ).strip()
    if household_value:
        conditions.append(
            f"CAST({expressions['household_article_count']} AS TEXT) LIKE :household_article_count"
        )
        params["household_article_count"] = f"%{household_value}%"
    linked_value = (
        linked_store_count if isinstance(linked_store_count, str) else ""
    ).strip()
    if linked_value:
        conditions.append(
            f"CAST({expressions['linked_store_count']} AS TEXT) LIKE :linked_store_count"
        )
        params["linked_store_count"] = f"%{linked_value}%"
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
    search: str = Query(default="", max_length=200),
    brand: str = Query(default="", max_length=200),
    primary_gtin: str = Query(default="", max_length=200),
    catalog_kind: str = Query(default="", max_length=50),
    product_type: str = Query(default="", max_length=200),
    gpc_brick_code: str = Query(default="", max_length=50),
    gpc_brick_name: str = Query(default="", max_length=200),
    gpc_class: str = Query(default="", max_length=200),
    gpc_family: str = Query(default="", max_length=200),
    source: str = Query(default="", max_length=200),
    household_article_count: str = Query(default="", max_length=50),
    linked_store_count: str = Query(default="", max_length=50),
    article_classification: str = Query(default="", max_length=200),
    sort_by: str = Query(default="name", max_length=50),
    sort_direction: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=10, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    started = perf_counter()
    if "global_products" not in _tables():
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    # Listing must be read-only and page-sized. GPC repair is performed by
    # its dedicated write flows, not on every page view.
    gpc_done = perf_counter()

    select_parts, joins, expressions = _catalog_projection()
    where_sql, params = _catalog_where(
        expressions,
        name,
        search,
        brand,
        primary_gtin,
        catalog_kind,
        product_type,
        gpc_brick_code,
        gpc_brick_name,
        gpc_class,
        gpc_family,
        source,
        household_article_count,
        linked_store_count,
        article_classification,
    )
    normalized_sort_by = sort_by if isinstance(sort_by, str) else "name"
    normalized_sort_direction = sort_direction if isinstance(sort_direction, str) else "asc"
    normalized_limit = limit if isinstance(limit, int) else 10
    normalized_offset = offset if isinstance(offset, int) else 0
    order_expression = expressions.get(normalized_sort_by, expressions["name"])
    direction = "DESC" if normalized_sort_direction.lower() == "desc" else "ASC"
    if normalized_sort_by in {"name", "catalog_kind", "brand", "primary_gtin", "product_type", "gpc_brick_code", "gpc_brick_name", "gpc_class_name", "gpc_family_name", "source"} or normalized_sort_by == "article_classification":
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
    page_params = {**params, "limit": normalized_limit, "offset": normalized_offset}
    with engine.begin() as conn:
        total = int(conn.execute(text(count_sql), params).scalar() or 0)
        count_done = perf_counter()
        items = [
            dict(row)
            for row in conn.execute(text(page_sql), page_params).mappings().all()
        ]
    page_done = perf_counter()
    if page_done - started >= 0.5:
        logging.getLogger("uvicorn.error").info(
            "catalog_list_timing total_ms=%.1f setup_ms=%.1f count_ms=%.1f page_ms=%.1f items=%d",
            (page_done-started)*1000, (gpc_done-started)*1000, (count_done-gpc_done)*1000,
            (page_done-count_done)*1000, len(items),
        )
    return {
        "items": items,
        "total": total,
        "limit": normalized_limit,
        "offset": normalized_offset,
    }



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


def _require_catalog_gtin_contributor() -> None:
    """Permit a narrow new-identity contribution by a platform catalog editor
    or an authenticated household owner/admin. No other Catalogus mutations
    or replacement of existing GTINs are authorized by this fallback.
    """
    try:
        require_platform_permission_from_session(CATALOG_IMAGE_UPDATE_PERMISSION)
        return
    except HTTPException as error:
        if error.status_code != 403:
            raise
    require_household_admin_from_session()



def _ed2_barcode_tables_ready() -> None:
    required = {"ed2_manual_barcodes", "external_article_product_links", "global_products"}
    if not required.issubset(_tables()):
        raise HTTPException(status_code=503, detail="Handmatige barcode-opslag is nog niet beschikbaar")


def _ed2_normalized_source(conn, receipt_item_id: str) -> dict[str, str]:
    try:
        identity = resolve_external_article_identity(conn, receipt_item_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Bonartikel bestaat niet meer") from error
    return {
        "retailer_code": normalize_external_link_retailer_code(identity["retailer_code"]),
        "receipt_text_normalized": normalize_external_link_receipt_text(identity["receipt_text"]),
        "external_article_code": normalize_external_link_article_code(identity["external_article_code"]),
    }


def _ed2_require_unlinked(conn, identity: dict[str, str]) -> None:
    # A receipt article code is the strongest retailer-scoped identity.
    # Never treat another item with the same receipt text but a different
    # article code as a collision. Only fall back to name when code is absent.
    if identity["external_article_code"]:
        predicate = "external_article_code = :external_article_code"
    elif identity["receipt_text_normalized"]:
        predicate = (
            "receipt_text_normalized = :receipt_text_normalized "
            "AND COALESCE(TRIM(external_article_code), '') = ''"
        )
    else:
        raise HTTPException(status_code=422, detail="Een stabiele bonartikelidentiteit ontbreekt")
    collision = conn.execute(text(
        "SELECT id FROM external_article_product_links "
        "WHERE retailer_code = :retailer_code AND status IN ('confirmed', 'classification_pending') "
        "AND " + predicate + " LIMIT 1"
    ), identity).first()
    if collision:
        raise HTTPException(status_code=409, detail="Dit bonartikel heeft al een Cataloguskoppeling of wacht op classificatie")


@router.get("/ed2/curated-matching-batch/preview")
def preview_ed2_curated_matching_batch(
    target_product_id: str | None = Query(default=None, max_length=200),
):
    """Curated central identity suggestions, never writes or invents barcodes."""
    require_platform_permission_from_session("platform.external_products.view")
    with engine.connect() as conn:
        try:
            return matching_batch_preview(conn, target_product_id=target_product_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/ed2/curated-matching-batch/confirm")
def confirm_ed2_curated_matching_batch(payload: Ed2CuratedMatchingBatchConfirmation):
    actor = require_platform_permission_from_session("platform.external_products.link_existing")
    if not (actor.is_platform_superuser or actor.is_frontteam):
        raise HTTPException(status_code=403, detail="Alleen bevoegde Superusers en Frontteamleden mogen centrale matches vastleggen.")
    if not re.fullmatch(r"[0-9a-f]{64}", payload.fingerprint):
        raise HTTPException(status_code=422, detail="De vooraf beoordeelde matchinglijst ontbreekt.")
    with engine.begin() as conn:
        try:
            return confirm_matching_batch(
                conn, target_product_id=payload.target_product_id,
                receipt_item_ids=payload.receipt_item_ids,
                expected_fingerprint=payload.fingerprint,
                actor_id=actor.user_id,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/ed2/courgette-family/options")
def ed2_courgette_family_options(receipt_item_id: str = Query(..., min_length=1, max_length=200)):
    require_platform_permission_from_session("platform.external_products.view")
    with engine.connect() as conn:
        try:
            source = resolve_external_article_identity(conn, receipt_item_id)
            return family_options(conn, source)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/ed2/courgette-family/confirm")
def confirm_ed2_courgette_family(payload: Ed2CourgetteFamilyConfirmation):
    actor = require_platform_permission_from_session("platform.external_products.link_existing")
    if not (actor.is_platform_superuser or actor.is_frontteam):
        raise HTTPException(status_code=403, detail="Alleen geautoriseerde Superusers en Frontteamleden mogen centrale artikelidentiteiten bevestigen.")
    if not re.fullmatch(r"[0-9a-f]{64}", payload.fingerprint):
        raise HTTPException(status_code=422, detail="De kandidaatgegevens zijn onjuist.")
    if payload.match_mode not in {"same_product", "synonym_variant"}:
        raise HTTPException(status_code=422, detail="Onbekende bevestigingswijze.")
    with engine.begin() as conn:
        try:
            source = resolve_external_article_identity(conn, payload.receipt_item_id)
            return confirm_courgette_receipt(
                conn, source=source, receipt_item_id=payload.receipt_item_id,
                target_product_id=payload.target_product_id,
                match_mode=payload.match_mode,
                expected_fingerprint=payload.fingerprint,
                actor_id=actor.user_id,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/ed2/manual-barcodes")
def list_ed2_manual_barcodes():
    """Show explicit GTIN evidence separately from verified Catalogus/OFF links."""
    require_platform_permission_from_session("platform.external_products.view")
    _ed2_barcode_tables_ready()
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT retailer_code, receipt_text_normalized, external_article_code, gtin "
            "FROM ed2_manual_barcodes ORDER BY retailer_code, receipt_text_normalized"
        )).mappings().all()
    return {"items": [dict(row) for row in rows]}



@router.post("/ed2/manual-barcodes/lidl/preview-correction")
def preview_ed2_lidl_barcode_correction(payload: Ed2LidlBarcodeCorrectionPreviewRequest):
    """Read-only impact preview; never alter an old Lidl/household/receipt row."""
    require_platform_permission_from_session("platform.external_products.link_existing")
    _ed2_barcode_tables_ready()
    if not {"product_identities", "auth_audit_log"}.issubset(_tables()):
        raise HTTPException(status_code=503, detail="Barcodecorrectie en audit zijn niet beschikbaar.")
    try:
        with engine.begin() as conn:
            source = resolve_external_article_identity(
                conn, str(payload.receipt_item_id or "").strip()
            )
            return preview_lidl_barcode_correction(
                conn, source=source,
                receipt_item_id=str(payload.receipt_item_id or "").strip(),
                new_gtin=payload.new_gtin,
                household_table=_household_table(),
            )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/ed2/manual-barcodes/lidl/confirm-correction")
def confirm_ed2_lidl_barcode_correction(payload: Ed2LidlBarcodeCorrectionConfirmRequest):
    """Explicit one-item correction; preview proof and all writes are atomic."""
    actor = require_platform_permission_from_session(
        "platform.external_products.link_existing"
    )
    _ed2_barcode_tables_ready()
    if not {"product_identities", "auth_audit_log"}.issubset(_tables()):
        raise HTTPException(status_code=503, detail="Barcodecorrectie en audit zijn niet beschikbaar.")
    if len(payload.preview_fingerprint) != 64 or any(
        char not in "0123456789abcdef" for char in payload.preview_fingerprint
    ):
        raise HTTPException(status_code=422, detail="De gevolgencontrole ontbreekt.")
    try:
        with engine.begin() as conn:
            source = resolve_external_article_identity(
                conn, str(payload.receipt_item_id or "").strip()
            )
            return confirm_lidl_barcode_correction(
                conn, source=source,
                receipt_item_id=str(payload.receipt_item_id or "").strip(),
                new_gtin=payload.new_gtin,
                expected_old_gtin=payload.expected_old_gtin,
                preview_fingerprint=payload.preview_fingerprint,
                actor_user_id=actor.user_id,
                household_table=_household_table(),
            )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/ed2/manual-barcodes/materialize-existing")
def materialize_existing_ed2_manual_barcodes(payload: Ed2HistoricalBarcodesRequest):
    """Explicit, all-or-nothing Catalogus resolution of previously saved barcodes.

    Every selected receipt identity is resolved server-side and must already
    have exactly the selected stored GTIN. No OFF, receipt, household, stock
    or synonym writes; any missing/changed/conflicting evidence rolls back
    the entire batch. This endpoint is never called on list/GET or startup.
    """
    actor = require_platform_permission_from_session(
        "platform.external_products.link_existing"
    )
    _ed2_barcode_tables_ready()
    if "product_identities" not in _tables():
        raise HTTPException(status_code=503, detail="Catalogus-identiteitstabel ontbreekt.")
    # Stable order for concurrent, overlapping bulk requests.
    selections = sorted(payload.selections, key=lambda item: item.receipt_item_id)
    results = []
    seen_sources = set()
    try:
        with engine.begin() as conn:
            for selection in selections:
                try:
                    source = resolve_external_article_identity(
                        conn, str(selection.receipt_item_id).strip()
                    )
                except ValueError as error:
                    raise HTTPException(
                        status_code=404,
                        detail="Een geselecteerd bonartikel bestaat niet meer."
                    ) from error
                # Resolve canonical tuple server-side; a second receipt row
                # for the same article cannot silently count as new evidence.
                source_key = (
                    normalize_external_link_retailer_code(source["retailer_code"]),
                    normalize_external_link_receipt_text(source["receipt_text"]),
                    normalize_external_link_article_code(source["external_article_code"]),
                )
                if source_key in seen_sources:
                    raise ValueError(
                        "De selectie bevat dezelfde winkelartikelidentiteit meerdere keren."
                    )
                seen_sources.add(source_key)
                results.append(materialize_saved_ed2_barcode(
                    conn,
                    retailer_code=source["retailer_code"],
                    receipt_text=source["receipt_text"],
                    external_article_code=source["external_article_code"],
                    barcode=selection.gtin,
                    confirmed_by=actor.user_id,
                    require_existing=True,
                ))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "ok": True,
        "processed": len(results),
        "catalog_links_created": sum(
            result["status"] == "confirmed" for result in results
        ),
        "already_confirmed": sum(
            result["status"] == "already_confirmed" for result in results
        ),
        "catalog_products_created": sum(
            bool(result["catalog_product_created"]) for result in results
        ),
        "household_changes": 0,
        "stock_changes": 0,
    }


@router.post("/ed2/manual-barcodes")
def save_ed2_manual_barcode(payload: Ed2ManualBarcodeRequest):
    """Saved barcode is sufficient Catalogus identity evidence, without OFF.

    The normal path saves an idempotent product link; an explicit Superuser
    OFF metadata override remains separate. No receipts or stock are changed.
    """
    actor_session = require_platform_permission_from_session("platform.external_products.link_existing")
    if payload.import_off_product_override:
        if not payload.allow_off_mismatch or not resolve_current_server_session().is_platform_superuser:
            raise HTTPException(status_code=403, detail="Alleen de Superuser mag een OFF-afwijking volledig koppelen.")
    _ed2_barcode_tables_ready()
    validation = validate_barcode(payload.gtin, "gtin")
    if not validation["valid"]:
        message = "; ".join(error["message"] for error in validation["errors"])
        raise HTTPException(status_code=422, detail=message or "Ongeldige barcode")
    gtin = validation["normalized_value"]
    receipt_item_id = str(payload.receipt_item_id or "").strip()
    if not payload.import_off_product_override:
        # A saved barcode is already confirmed evidence under the current PO
        # contract. Neither OFF nor a GS1 classification is a prerequisite.
        try:
            with engine.begin() as conn:
                try:
                    source = resolve_external_article_identity(conn, receipt_item_id)
                except ValueError as error:
                    raise HTTPException(
                        status_code=404, detail="Bonartikel bestaat niet meer."
                    ) from error
                result = materialize_saved_ed2_barcode(
                    conn, retailer_code=source["retailer_code"],
                    receipt_text=source["receipt_text"],
                    external_article_code=source["external_article_code"],
                    barcode=gtin, confirmed_by=actor_session.user_id,
                )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "saved": True, "source": "manual", "gtin": gtin,
            "off_found": False, "off_unavailable": False,
            "classification_pending": False, "photo_loaded": False,
            "catalog_linked": True,
            "catalog_product_created": result["catalog_product_created"],
            "global_product_id": result["global_product_id"],
            "barcode_scope": result["barcode_scope"], "stock_changes": 0,
        }

    with engine.begin() as conn:
        identity = _ed2_normalized_source(conn, receipt_item_id)
        _ed2_require_unlinked(conn, identity)
        existing = conn.execute(text(
            "SELECT gtin FROM ed2_manual_barcodes "
            "WHERE retailer_code = :retailer_code "
            "AND receipt_text_normalized = :receipt_text_normalized "
            "AND external_article_code = :external_article_code"
        ), identity).scalar()
        if existing and str(existing) != gtin:
            raise HTTPException(status_code=409, detail="Dit bonartikel heeft al een andere handmatig opgeslagen barcode")

    # The original source is resolved again by the canonical OFF search service.
    # Do not accept candidate names, image URLs or OFF identities from the browser.
    off_unavailable = False
    try:
        search = search_off_candidates({
            "receipt_item_id": receipt_item_id, "mode": "manual", "gtin": gtin, "limit": 1,
        })
    except OffUnavailableError:
        # A network outage must not block explicit user-entered barcode evidence.
        # Do NOT claim that OFF has no match: the lookup was not completed.
        off_unavailable = True
        search = {"results": []}
    except OffSearchError as error:
        # Unexpected lookup/identity errors must not be treated as OFF downtime.
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    results = search.get("results") or []
    # OFF indexes a GTIN-14 with one leading zero under its equivalent EAN-13.
    # Compare canonical identities, not their textual width. Never remove a
    # nonzero packaging indicator or accept a different product GTIN.
    off_gtin = gtin[1:] if len(gtin) == 14 and gtin.startswith("0") else gtin
    if results:
        candidate = results[0]
        if candidate.get("identity_compatible") is False:
            if not payload.allow_off_mismatch:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "off_identity_mismatch",
                        "message": "De OFF-productgegevens passen niet veilig bij dit bonartikel. Er is niets opgeslagen.",
                        "product_name": str(candidate.get("product_name") or ""),
                        "brand": str(candidate.get("brand") or ""),
                        "quantity": str(candidate.get("quantity") or ""),
                        "gtin": gtin,
                        "conflict_reason": str(candidate.get("identity_conflict_message") or ""),
                    },
                )
            # Existing manual entry still supports barcode-only override.
            # The Superuser import choice instead confirms all OFF metadata.
            if not payload.import_off_product_override:
                results = []
    if payload.allow_off_mismatch and not payload.import_off_product_override:
        results = []
    if results:
        candidate = results[0]
        # OFF product is resolved on the server for the exact GTIN. Never accept
        # client-provided metadata or bypass signature/receipt validation.
        if str(candidate.get("gtin") or "") != off_gtin:
            raise HTTPException(status_code=409, detail="OFF-barcode wijkt af van de geselecteerde barcode.")
        proof = candidate.get("selection_proof")
        if payload.import_off_product_override:
            # Re-issue for this exact bonartikel from the trusted OFF response.
            # Preserve signature binding to the OFF-canonical GTIN, not the
            # optional leading zero in the uploaded GTIN-14.
            proof = issue_manual_off_proof(receipt_item_id, candidate)
        if not proof:
            raise HTTPException(status_code=409, detail="OFF kon deze barcode niet betrouwbaar bevestigen")
        try:
            result = confirm_selected_off_catalog_product({
                "receipt_item_id": receipt_item_id,
                "gtin": off_gtin,
                "selection_proof": proof,
                **({"override_private_label_conflict": True}
                   if payload.import_off_product_override and candidate.get("identity_compatible") is False
                   else {}),
            })
        except ValueError as error:
            # A receipt-bound proof mismatch is a product-identity warning,
            # not authorization to bypass signature checks or link OFF data.
            # Offer the Superuser an explicit GTIN-only choice instead.
            if str(error) == "Dit zoekresultaat hoort niet bij het geselecteerde bonartikel.":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "off_identity_mismatch",
                        "message": "Dit OFF-zoekresultaat hoort niet bij het geselecteerde bonartikel. Er is niets opgeslagen.",
                        "product_name": str(candidate.get("product_name") or ""),
                        "brand": str(candidate.get("brand") or ""),
                        "quantity": str(candidate.get("quantity") or ""),
                        "gtin": gtin,
                        "conflict_reason": str(error),
                    },
                ) from error
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {
            "saved": bool(result.get("ok")), "source": "off",
            "gtin": gtin, "off_found": True,
            "classification_pending": bool(result.get("classification_pending")),
            "photo_loaded": bool(candidate.get("image_url")),
        }

    # OFF is optional metadata, not identity authority. A user-entered saved
    # barcode must *always* be materialised to Catalogus in the same atomic
    # transaction; this exceptional route must not recreate legacy orphans.
    # Existing historical/retailer conflicts remain fail-closed.
    try:
        with engine.begin() as conn:
            source = resolve_external_article_identity(conn, receipt_item_id)
            result = materialize_saved_ed2_barcode(
                conn, retailer_code=source["retailer_code"],
                receipt_text=source["receipt_text"],
                external_article_code=source["external_article_code"],
                barcode=gtin, confirmed_by=actor_session.user_id,
            )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "saved": True, "source": "manual", "gtin": gtin, "off_found": False,
        "off_unavailable": off_unavailable, "classification_pending": False,
        "photo_loaded": False, "catalog_linked": True,
        "catalog_product_created": result["catalog_product_created"],
        "global_product_id": result["global_product_id"],
        "barcode_scope": result["barcode_scope"], "stock_changes": 0,
    }


@router.put("/{global_product_id}/name")
def update_catalog_product_name(global_product_id: str, payload: CatalogNameUpdateRequest):
    """Rename a shared Catalogus article without changing its identity or household links.

    Names are mutable presentation metadata, never barcode or receipt identity.
    The canonical fingerprint must stay in sync, so later imports do not
    accidentally recreate the article under its old name.
    """
    require_platform_permission_from_session(CATALOG_IMAGE_UPDATE_PERMISSION)
    product_columns = _columns("global_products")
    required = {
        "id", "name", "status", "primary_gtin", "brand", "variant",
        "size_value", "size_unit", "product_fingerprint",
    }
    if not required.issubset(product_columns):
        raise HTTPException(status_code=503, detail="De gezamenlijke Catalogus is niet beschikbaar")

    with engine.begin() as conn:
        lock = " FOR UPDATE" if conn.dialect.name == "postgresql" else ""
        current = conn.execute(
            text(
                "SELECT id, name, status, primary_gtin, brand, variant, "
                "size_value, size_unit, product_fingerprint "
                "FROM global_products WHERE id = :product_id" + lock
            ),
            {"product_id": global_product_id},
        ).mappings().first()
        if not current or str(current.get("status") or "").strip().lower() == "deleted":
            raise HTTPException(status_code=404, detail="Catalogusartikel niet gevonden")

        existing_name = str(current.get("name") or "").strip()
        if existing_name != payload.expected_name:
            raise HTTPException(
                status_code=409,
                detail="De artikelnaam is intussen gewijzigd. Vernieuw het artikel en probeer opnieuw.",
            )
        if existing_name == payload.name:
            return {"global_product_id": global_product_id, "name": existing_name, "changed": False}

        fingerprint = build_global_product_fingerprint(
            payload.name,
            current.get("brand"),
            current.get("variant"),
            current.get("size_value"),
            current.get("size_unit"),
        )
        # A changed name may not silently collapse onto another active,
        # unbarcoded product. Explicit identity linking remains a separate flow.
        conflict = conn.execute(
            text(
                "SELECT id FROM global_products "
                "WHERE product_fingerprint = :fingerprint AND id <> :product_id "
                "AND status = 'active' "
                "AND COALESCE(TRIM(primary_gtin), '') = '' LIMIT 1"
            ),
            {"fingerprint": fingerprint, "product_id": global_product_id},
        ).first()
        if conflict:
            raise HTTPException(
                status_code=409,
                detail="Deze naam hoort al bij een ander catalogusartikel. De artikelen worden niet automatisch samengevoegd.",
            )

        updated_at_sql = ", updated_at = CURRENT_TIMESTAMP" if "updated_at" in product_columns else ""
        updated = conn.execute(
            text(
                "UPDATE global_products SET name = :new_name, "
                "product_fingerprint = :fingerprint" + updated_at_sql
                + " WHERE id = :product_id AND name = :expected_name"
            ),
            {
                "new_name": payload.name,
                "fingerprint": fingerprint,
                "product_id": global_product_id,
                "expected_name": existing_name,
            },
        )
        if updated.rowcount != 1:
            raise HTTPException(
                status_code=409, detail="De artikelnaam is tussentijds gewijzigd. Probeer opnieuw.",
            )

    return {"global_product_id": global_product_id, "name": payload.name, "changed": True}


@router.put("/{global_product_id}/gtin")
def set_catalog_primary_gtin(
    global_product_id: str,
    payload: CatalogGtinUpdateRequest,
):
    """Register one verified GTIN on the shared product, never on a household stock row."""
    _require_catalog_gtin_contributor()
    required = {"id", "primary_gtin", "status"}
    if "global_products" not in _tables() or not required.issubset(_columns("global_products")):
        raise HTTPException(status_code=503, detail="De gedeelde Catalogus is niet beschikbaar")

    validation = validate_barcode(payload.gtin, "gtin")
    if not validation["valid"]:
        message = "; ".join(error["message"] for error in validation["errors"])
        raise HTTPException(status_code=422, detail=message or "Ongeldige barcode")
    gtin = validation["normalized_value"]

    product_columns = _columns("global_products")
    with engine.begin() as conn:
        # Serialize concurrent assignments of the same GTIN across different
        # products. A row lock alone does not protect another product's empty GTIN.
        if conn.dialect.name == "postgresql":
            conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:gtin))"),
                {"gtin": gtin},
            )

        lock = " FOR UPDATE" if conn.dialect.name == "postgresql" else ""
        existing = conn.execute(
            text("SELECT id, status, primary_gtin FROM global_products "
                 "WHERE id = :product_id" + lock),
            {"product_id": global_product_id},
        ).mappings().first()
        if not existing or str(existing.get("status") or "").lower() == "deleted":
            raise HTTPException(status_code=404, detail="Catalogusartikel niet gevonden")

        previous_gtin = str(existing.get("primary_gtin") or "").strip()
        if previous_gtin and previous_gtin != gtin:
            raise HTTPException(
                status_code=409,
                detail="Dit artikel heeft al een andere primaire barcode. Deze wordt niet automatisch overschreven.",
            )

        conflicting = conn.execute(
            text("SELECT id FROM global_products "
                 "WHERE primary_gtin = :gtin AND id <> :product_id LIMIT 1"),
            {"gtin": gtin, "product_id": global_product_id},
        ).first()
        if conflicting:
            raise HTTPException(
                status_code=409,
                detail="Deze barcode is al aan een ander catalogusartikel gekoppeld.",
            )

        # The shared identity table may contain legacy household-linked GTIN
        # evidence. Do not silently reassign an existing identity to this product.
        if "product_identities" in _tables():
            identity_columns = _columns("product_identities")
            if {"identity_type", "identity_value", "global_product_id"}.issubset(identity_columns):
                identity_conflict = conn.execute(
                    text("SELECT id FROM product_identities "
                         "WHERE identity_type IN ('gtin', 'ean', 'upc') "
                         "AND identity_value = :gtin "
                         "AND global_product_id IS NOT NULL "
                         "AND global_product_id <> :product_id LIMIT 1"),
                    {"gtin": gtin, "product_id": global_product_id},
                ).first()
                if identity_conflict:
                    raise HTTPException(
                        status_code=409,
                        detail="Deze barcode is al gekoppeld aan een andere productidentiteit.",
                    )

        if not previous_gtin:
            timestamp_sql = ", updated_at = CURRENT_TIMESTAMP" if "updated_at" in product_columns else ""
            conn.execute(
                text("UPDATE global_products SET primary_gtin = :gtin" + timestamp_sql
                     + " WHERE id = :product_id AND (primary_gtin IS NULL OR TRIM(primary_gtin) = '')"),
                {"gtin": gtin, "product_id": global_product_id},
            )

    return {"global_product_id": global_product_id, "gtin": gtin, "changed": not bool(previous_gtin)}


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
    with engine.begin() as conn:
        ensure_dutch_gpc_assignments(conn, [global_product_id])
    product = _catalog_row(global_product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Universeel artikel niet gevonden")
    return {
        "product": product,
        "identities": _identity_rows(global_product_id),
        "household_articles": _household_article_rows(global_product_id),
        "receipt_lines": _receipt_line_rows(global_product_id),
    }
