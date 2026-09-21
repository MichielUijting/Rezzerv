from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
import uuid

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

ALLOWED_UNITS = {"", "stuk", "stuks", "gram", "kilogram", "milliliter", "liter", "verpakking"}
ALLOWED_SEARCH_SCOPES = {"household_articles", "global_products", "product_types", "article_groups"}

SHOPPING_LIST_REQUIRED_COLUMNS = {
    "id",
    "household_id",
    "status",
    "created_at",
    "completed_at",
    "completed_by",
}
SHOPPING_LIST_ITEM_REQUIRED_COLUMNS = {
    "id",
    "shopping_list_id",
    "household_id",
    "article_name",
    "article_group_name",
    "product_type_name",
    "source_type",
    "source_id",
    "quantity",
    "volume",
    "unit",
    "size",
    "note",
    "checked",
    "created_at",
    "updated_at",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_columns(conn: Connection, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column.get("name") or "") for column in inspector.get_columns(table_name)}


def _table_indexes(conn: Connection, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {
        str(index.get("name") or "")
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }


def ensure_shopping_list_schema(conn: Connection) -> None:
    """Validate the Alembic-owned shopping-list schema without mutating it."""
    inspector = inspect(conn)
    table_names = set(inspector.get_table_names())
    missing_tables = {"shopping_lists", "shopping_list_items"} - table_names
    if missing_tables:
        raise RuntimeError(
            "Shopping-list schema is not migrated; missing tables: "
            + ", ".join(sorted(missing_tables))
        )

    missing_list_columns = SHOPPING_LIST_REQUIRED_COLUMNS - _table_columns(
        conn, "shopping_lists"
    )
    if missing_list_columns:
        raise RuntimeError(
            "Shopping-list schema is incomplete; shopping_lists missing columns: "
            + ", ".join(sorted(missing_list_columns))
        )

    missing_item_columns = SHOPPING_LIST_ITEM_REQUIRED_COLUMNS - _table_columns(
        conn, "shopping_list_items"
    )
    if missing_item_columns:
        raise RuntimeError(
            "Shopping-list schema is incomplete; shopping_list_items missing columns: "
            + ", ".join(sorted(missing_item_columns))
        )

    if "ux_shopping_lists_household_active" not in _table_indexes(
        conn, "shopping_lists"
    ):
        raise RuntimeError(
            "Shopping-list schema is incomplete; missing index "
            "ux_shopping_lists_household_active"
        )
    if "idx_shopping_list_items_active" not in _table_indexes(
        conn, "shopping_list_items"
    ):
        raise RuntimeError(
            "Shopping-list schema is incomplete; missing index "
            "idx_shopping_list_items_active"
        )


def _normalize_decimal(value: Any, field_name: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} moet een geldig getal zijn") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} mag niet negatief zijn")
    return parsed


def _database_number(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _normalize_unit(value: Any) -> str:
    unit = str(value or "").strip().lower()
    if unit not in ALLOWED_UNITS:
        raise ValueError("Ongeldige eenheid")
    return unit


def _serialize_decimal(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _serialize_item(row: Any) -> dict[str, Any]:
    payload = {
        "id": str(row.get("id") or ""),
        "shopping_list_id": str(row.get("shopping_list_id") or ""),
        "household_id": str(row.get("household_id") or ""),
        "article_name": str(row.get("article_name") or ""),
        "article_group_name": str(row.get("article_group_name") or ""),
        "product_type_name": str(row.get("product_type_name") or ""),
        "source_type": str(row.get("source_type") or "manual"),
        "source_id": str(row.get("source_id") or ""),
        "quantity": _serialize_decimal(row.get("quantity")),
        "volume": _serialize_decimal(row.get("volume")),
        "unit": str(row.get("unit") or ""),
        "size": str(row.get("size") or ""),
        "note": str(row.get("note") or ""),
        "checked": bool(row.get("checked")),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }
    row_keys = set(row.keys()) if hasattr(row, "keys") else set()
    if "image_url" in row_keys:
        payload["image_url"] = str(row.get("image_url") or "").strip()
    return payload


def _shopping_list_image_projection(conn: Connection) -> tuple[str, str]:
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    if "global_products" not in tables:
        return "'' AS image_url", ""

    product_columns = _table_columns(conn, "global_products")
    if not {"id", "image_url"}.issubset(product_columns):
        return "'' AS image_url", ""

    household_join = ""
    household_product_condition = ""
    if "household_articles" in tables:
        household_columns = _table_columns(conn, "household_articles")
        if {"id", "household_id", "global_product_id"}.issubset(household_columns):
            household_join = """
        LEFT JOIN household_articles ha
          ON lower(trim(COALESCE(sli.source_type, 'manual'))) = 'household_article'
         AND ha.id = sli.source_id
         AND ha.household_id = sli.household_id
            """
            household_product_condition = """
             OR (
                lower(trim(COALESCE(sli.source_type, 'manual'))) = 'household_article'
                AND gp.id = ha.global_product_id
             )
            """

    return (
        "COALESCE(gp.image_url, '') AS image_url",
        f"""
        {household_join}
        LEFT JOIN global_products gp
          ON (
              lower(trim(COALESCE(sli.source_type, 'manual'))) = 'global_product'
              AND gp.id = sli.source_id
          )
          {household_product_condition}
        """,
    )


def _first_column(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _search_simple_table(
    conn: Connection,
    *,
    table_name: str,
    query: str,
    household_id: str | None,
    source_type: str,
    label_candidates: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    columns = _table_columns(conn, table_name)
    if not columns:
        return []
    id_column = _first_column(columns, ("id", "key", "code", "product_type_id", "inventory_group_key"))
    label_column = _first_column(columns, label_candidates)
    if not id_column or not label_column:
        return []
    household_clause = ""
    parameters: dict[str, Any] = {"query": f"%{query.lower()}%", "limit": limit}
    if household_id is not None and "household_id" in columns:
        household_clause = "AND household_id = :household_id"
        parameters["household_id"] = household_id
    rows = conn.execute(text(f"""
        SELECT {id_column} AS source_id, {label_column} AS label
        FROM {table_name}
        WHERE lower(trim(COALESCE({label_column}, ''))) LIKE :query
          {household_clause}
        ORDER BY lower(trim(COALESCE({label_column}, '')))
        LIMIT :limit
    """), parameters).mappings().all()
    return [
        {
            "source_type": source_type,
            "source_id": str(row.get("source_id") or ""),
            "label": str(row.get("label") or "").strip(),
            "article_name": str(row.get("label") or "").strip(),
            "article_group_name": str(row.get("label") or "").strip() if source_type == "article_group" else "",
            "product_type_name": str(row.get("label") or "").strip() if source_type == "product_type" else "",
        }
        for row in rows if str(row.get("label") or "").strip()
    ]


def _global_product_type_expression(conn: Connection) -> str:
    tables = set(inspect(conn).get_table_names())
    expressions: list[str] = []

    if {"global_product_gpc_bricks", "gpc_bricks"}.issubset(tables):
        translation_expression = "NULL"
        if "gpc_translations" in tables:
            translation_columns = _table_columns(conn, "gpc_translations")
            if {"entity_type", "entity_code", "language_code", "translated_text"}.issubset(translation_columns):
                translation_expression = """
                    (SELECT tr.translated_text
                     FROM gpc_translations tr
                     WHERE tr.entity_type = 'brick'
                       AND tr.entity_code = gpgb.brick_code
                       AND tr.language_code = 'nl'
                     LIMIT 1)
                """
        expressions.append(f"""
            (SELECT COALESCE({translation_expression}, gb.description, '')
             FROM global_product_gpc_bricks gpgb
             JOIN gpc_bricks gb ON gb.brick_code = gpgb.brick_code
             WHERE gpgb.global_product_id = gp.id
             ORDER BY gpgb.brick_code
             LIMIT 1)
        """)

    if {"product_group_memberships", "product_inventory_groups"}.issubset(tables):
        expressions.append("""
            (SELECT pig.display_name
             FROM product_group_memberships pgm
             JOIN product_inventory_groups pig
               ON pig.inventory_group_key = pgm.inventory_group_key
             WHERE pgm.global_product_id = gp.id
               AND COALESCE(pgm.active, 1) = 1
               AND COALESCE(pig.active, 1) = 1
             ORDER BY pig.display_name
             LIMIT 1)
        """)

    if not expressions:
        return "''"
    return "COALESCE(" + ", ".join(expressions + ["''"]) + ")"


def _search_global_products(
    conn: Connection,
    *,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    columns = _table_columns(conn, "global_products")
    if not {"id", "name", "primary_gtin"}.issubset(columns):
        return []

    brand_expression = "COALESCE(gp.brand, '')" if "brand" in columns else "''"
    image_expression = "COALESCE(gp.image_url, '')" if "image_url" in columns else "''"
    product_type_expression = _global_product_type_expression(conn)
    status_condition = (
        "AND lower(trim(COALESCE(gp.status, 'active'))) <> 'deleted'"
        if "status" in columns
        else ""
    )
    query_conditions = ["lower(trim(COALESCE(gp.name, ''))) LIKE :query"]
    if "brand" in columns:
        query_conditions.append("lower(trim(COALESCE(gp.brand, ''))) LIKE :query")
    query_conditions.append("lower(trim(COALESCE(gp.primary_gtin, ''))) LIKE :query")

    rows = conn.execute(text(f"""
        SELECT gp.id AS source_id,
               gp.name AS label,
               {brand_expression} AS brand,
               COALESCE(gp.primary_gtin, '') AS primary_gtin,
               {image_expression} AS image_url,
               {product_type_expression} AS product_type_name
        FROM global_products gp
        WHERE trim(COALESCE(gp.primary_gtin, '')) <> ''
          {status_condition}
          AND ({" OR ".join(query_conditions)})
        ORDER BY
          CASE
            WHEN lower(trim(COALESCE(gp.name, ''))) = :exact_query THEN 0
            WHEN lower(trim(COALESCE(gp.name, ''))) LIKE :prefix_query THEN 1
            ELSE 2
          END,
          lower(trim(COALESCE(gp.name, ''))),
          gp.id
        LIMIT :limit
    """), {
        "query": f"%{query.lower()}%",
        "exact_query": query.lower(),
        "prefix_query": f"{query.lower()}%",
        "limit": limit,
    }).mappings().all()

    return [
        {
            "source_type": "global_product",
            "source_id": str(row.get("source_id") or ""),
            "label": str(row.get("label") or "").strip(),
            "article_name": str(row.get("label") or "").strip(),
            "article_group_name": "",
            "product_type_name": str(row.get("product_type_name") or "").strip(),
            "brand": str(row.get("brand") or "").strip(),
            "primary_gtin": str(row.get("primary_gtin") or "").strip(),
            "image_url": str(row.get("image_url") or "").strip(),
        }
        for row in rows
        if str(row.get("label") or "").strip()
    ]


def search_shopping_catalog(
    conn: Connection,
    household_id: str,
    *,
    scope: str,
    query: str,
    limit: int = 20,
) -> dict[str, Any]:
    normalized_scope = str(scope or "").strip().lower()
    normalized_query = " ".join(str(query or "").strip().split())
    if normalized_scope not in ALLOWED_SEARCH_SCOPES:
        raise ValueError("Ongeldige zoekbron")
    if len(normalized_query) < 2:
        return {"scope": normalized_scope, "query": normalized_query, "items": [], "total": 0}
    safe_limit = max(1, min(int(limit or 20), 50))

    if normalized_scope == "article_groups":
        items = _search_simple_table(
            conn,
            table_name="article_groups",
            query=normalized_query,
            household_id=str(household_id),
            source_type="article_group",
            label_candidates=("name", "display_name", "article_group_name"),
            limit=safe_limit,
        )
    elif normalized_scope == "global_products":
        items = _search_global_products(
            conn,
            query=normalized_query,
            limit=safe_limit,
        )
    elif normalized_scope == "product_types":
        items = []
        for table_name in ("product_types", "global_product_types", "product_inventory_groups"):
            items.extend(_search_simple_table(
                conn,
                table_name=table_name,
                query=normalized_query,
                household_id=None,
                source_type="product_type",
                label_candidates=("name", "display_name", "product_type_name", "inventory_group_name"),
                limit=safe_limit,
            ))
            if items:
                break
    else:
        columns = _table_columns(conn, "household_articles")
        items = []
        if columns:
            id_column = _first_column(columns, ("id", "household_article_id"))
            label_column = _first_column(columns, ("article_name", "name", "display_name"))
            group_column = _first_column(columns, ("article_group_name", "group_name"))
            product_type_column = _first_column(columns, ("product_type_name", "type_name"))
            if id_column and label_column:
                rows = conn.execute(text(f"""
                    SELECT {id_column} AS source_id,
                           {label_column} AS label,
                           {group_column if group_column else 'NULL'} AS article_group_name,
                           {product_type_column if product_type_column else 'NULL'} AS product_type_name
                    FROM household_articles
                    WHERE household_id = :household_id
                      AND lower(trim(COALESCE({label_column}, ''))) LIKE :query
                    ORDER BY lower(trim(COALESCE({label_column}, '')))
                    LIMIT :limit
                """), {
                    "household_id": str(household_id),
                    "query": f"%{normalized_query.lower()}%",
                    "limit": safe_limit,
                }).mappings().all()
                items = [{
                    "source_type": "household_article",
                    "source_id": str(row.get("source_id") or ""),
                    "label": str(row.get("label") or "").strip(),
                    "article_name": str(row.get("label") or "").strip(),
                    "article_group_name": str(row.get("article_group_name") or ""),
                    "product_type_name": str(row.get("product_type_name") or ""),
                } for row in rows if str(row.get("label") or "").strip()]

    deduplicated: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("source_type") or ""), str(item.get("source_id") or item.get("label") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(item)
        if len(deduplicated) >= safe_limit:
            break
    return {"scope": normalized_scope, "query": normalized_query, "items": deduplicated, "total": len(deduplicated)}


def get_or_create_active_list(conn: Connection, household_id: str) -> dict[str, Any]:
    ensure_shopping_list_schema(conn)
    household_id = str(household_id or "").strip()
    if not household_id:
        raise ValueError("Huishouden ontbreekt")
    row = conn.execute(text("""
        SELECT id, household_id, status, created_at, completed_at, completed_by
        FROM shopping_lists
        WHERE household_id = :household_id AND status = 'active'
        LIMIT 1
    """), {"household_id": household_id}).mappings().first()
    if not row:
        list_id = str(uuid.uuid4())
        created_at = _utc_now_iso()
        conn.execute(text("""
            INSERT INTO shopping_lists(id, household_id, status, created_at)
            VALUES (:id, :household_id, 'active', :created_at)
        """), {"id": list_id, "household_id": household_id, "created_at": created_at})
        row = {"id": list_id, "household_id": household_id, "status": "active", "created_at": created_at, "completed_at": None, "completed_by": None}
    return dict(row)


def get_active_shopping_list(conn: Connection, household_id: str) -> dict[str, Any]:
    active = get_or_create_active_list(conn, household_id)
    image_expression, image_joins = _shopping_list_image_projection(conn)
    rows = conn.execute(text(f"""
        SELECT sli.id, sli.shopping_list_id, sli.household_id, sli.article_name, sli.article_group_name,
               sli.product_type_name, sli.source_type, sli.source_id, sli.quantity, sli.volume, sli.unit,
               sli.size, sli.note, sli.checked, sli.created_at, sli.updated_at,
               {image_expression}
        FROM shopping_list_items sli
        {image_joins}
        WHERE sli.shopping_list_id = :shopping_list_id AND sli.household_id = :household_id
        ORDER BY sli.checked ASC, lower(sli.article_name) ASC, sli.created_at ASC
    """), {"shopping_list_id": active["id"], "household_id": str(household_id)}).mappings().all()
    return {**active, "items": [_serialize_item(row) for row in rows], "item_count": len(rows)}


def add_shopping_list_item(conn: Connection, household_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    active = get_or_create_active_list(conn, household_id)
    article_name = " ".join(str(payload.get("article_name") or payload.get("label") or "").strip().split())
    if not article_name:
        raise ValueError("Artikelnaam is verplicht")

    requested_quantity = _database_number(_normalize_decimal(payload.get("quantity"), "Aantal"))
    volume = _database_number(_normalize_decimal(payload.get("volume"), "Volume"))
    unit = _normalize_unit(payload.get("unit"))
    source_type = str(payload.get("source_type") or "manual").strip().lower() or "manual"
    source_id = str(payload.get("source_id") or "").strip()
    canonical_candidate = bool(source_id and source_type != "manual")
    now = _utc_now_iso()

    if canonical_candidate:
        existing = conn.execute(text("""
            SELECT *
            FROM shopping_list_items
            WHERE shopping_list_id = :shopping_list_id
              AND household_id = :household_id
              AND lower(trim(COALESCE(source_type, 'manual'))) = :source_type
              AND trim(COALESCE(source_id, '')) = :source_id
            ORDER BY created_at ASC, id ASC
            LIMIT 1
        """), {
            "shopping_list_id": active["id"],
            "household_id": str(household_id),
            "source_type": source_type,
            "source_id": source_id,
        }).mappings().first()

        if existing:
            current_quantity = _serialize_decimal(existing.get("quantity"))
            next_quantity = (current_quantity if current_quantity is not None else 1.0) + (
                requested_quantity if requested_quantity is not None else 1.0
            )
            conn.execute(text("""
                UPDATE shopping_list_items
                SET article_name = :article_name,
                    article_group_name = :article_group_name,
                    product_type_name = :product_type_name,
                    quantity = :quantity,
                    checked = 0,
                    updated_at = :updated_at
                WHERE id = :id
                  AND shopping_list_id = :shopping_list_id
                  AND household_id = :household_id
            """), {
                "article_name": article_name,
                "article_group_name": str(payload.get("article_group_name") or existing.get("article_group_name") or "").strip(),
                "product_type_name": str(payload.get("product_type_name") or existing.get("product_type_name") or "").strip(),
                "quantity": next_quantity,
                "updated_at": now,
                "id": str(existing["id"]),
                "shopping_list_id": active["id"],
                "household_id": str(household_id),
            })
            row = conn.execute(
                text("SELECT * FROM shopping_list_items WHERE id = :id AND household_id = :household_id"),
                {"id": str(existing["id"]), "household_id": str(household_id)},
            ).mappings().one()
            return _serialize_item(row)

    item_id = str(uuid.uuid4())
    quantity = requested_quantity
    if canonical_candidate and quantity is None:
        quantity = 1.0

    values = {
        "id": item_id,
        "shopping_list_id": active["id"],
        "household_id": str(household_id),
        "article_name": article_name,
        "article_group_name": str(payload.get("article_group_name") or "").strip(),
        "product_type_name": str(payload.get("product_type_name") or "").strip(),
        "source_type": source_type,
        "source_id": source_id,
        "quantity": quantity,
        "volume": volume,
        "unit": unit,
        "size": str(payload.get("size") or "").strip(),
        "note": str(payload.get("note") or "").strip(),
        "created_at": now,
        "updated_at": now,
    }
    conn.execute(text("""
        INSERT INTO shopping_list_items(
            id, shopping_list_id, household_id, article_name, article_group_name,
            product_type_name, source_type, source_id, quantity, volume, unit,
            size, note, checked, created_at, updated_at
        ) VALUES (
            :id, :shopping_list_id, :household_id, :article_name, :article_group_name,
            :product_type_name, :source_type, :source_id, :quantity, :volume, :unit,
            :size, :note, 0, :created_at, :updated_at
        )
    """), values)
    row = conn.execute(text("SELECT * FROM shopping_list_items WHERE id = :id"), {"id": item_id}).mappings().one()
    return _serialize_item(row)
def update_shopping_list_item(conn: Connection, household_id: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    ensure_shopping_list_schema(conn)
    existing = conn.execute(text("SELECT * FROM shopping_list_items WHERE id = :id AND household_id = :household_id LIMIT 1"), {"id": str(item_id), "household_id": str(household_id)}).mappings().first()
    if not existing:
        return None
    article_name = " ".join(str(payload.get("article_name", existing["article_name"]) or "").strip().split())
    if not article_name:
        raise ValueError("Artikelnaam is verplicht")
    values = {
        "article_name": article_name,
        "article_group_name": str(payload.get("article_group_name", existing.get("article_group_name") or "") or "").strip(),
        "product_type_name": str(payload.get("product_type_name", existing.get("product_type_name") or "") or "").strip(),
        "quantity": _database_number(_normalize_decimal(payload.get("quantity", existing.get("quantity")), "Aantal")),
        "volume": _database_number(_normalize_decimal(payload.get("volume", existing.get("volume")), "Volume")),
        "unit": _normalize_unit(payload.get("unit", existing.get("unit"))),
        "size": str(payload.get("size", existing.get("size") or "") or "").strip(),
        "note": str(payload.get("note", existing.get("note") or "") or "").strip(),
        "checked": 1 if bool(payload.get("checked", bool(existing.get("checked")))) else 0,
        "updated_at": _utc_now_iso(),
        "id": str(item_id),
        "household_id": str(household_id),
    }
    conn.execute(text("""
        UPDATE shopping_list_items
        SET article_name = :article_name,
            article_group_name = :article_group_name,
            product_type_name = :product_type_name,
            quantity = :quantity,
            volume = :volume,
            unit = :unit,
            size = :size,
            note = :note,
            checked = :checked,
            updated_at = :updated_at
        WHERE id = :id AND household_id = :household_id
    """), values)
    row = conn.execute(text("SELECT * FROM shopping_list_items WHERE id = :id AND household_id = :household_id"), {"id": str(item_id), "household_id": str(household_id)}).mappings().one()
    return _serialize_item(row)


def delete_shopping_list_item(conn: Connection, household_id: str, item_id: str) -> bool:
    ensure_shopping_list_schema(conn)
    result = conn.execute(text("DELETE FROM shopping_list_items WHERE id = :id AND household_id = :household_id"), {"id": str(item_id), "household_id": str(household_id)})
    return bool(result.rowcount)


def complete_active_shopping_list(conn: Connection, household_id: str, completed_by: str) -> dict[str, Any]:
    active = get_or_create_active_list(conn, household_id)
    item_count = int(conn.execute(text("SELECT COUNT(*) FROM shopping_list_items WHERE shopping_list_id = :shopping_list_id AND household_id = :household_id"), {"shopping_list_id": active["id"], "household_id": str(household_id)}).scalar_one() or 0)
    completed_at = _utc_now_iso()
    conn.execute(text("""
        UPDATE shopping_lists
        SET status = 'completed', completed_at = :completed_at, completed_by = :completed_by
        WHERE id = :id AND household_id = :household_id AND status = 'active'
    """), {"completed_at": completed_at, "completed_by": str(completed_by or ""), "id": active["id"], "household_id": str(household_id)})
    next_active = get_or_create_active_list(conn, household_id)
    return {"status": "completed", "completed_list_id": active["id"], "completed_at": completed_at, "completed_item_count": item_count, "active_list_id": next_active["id"], "items": []}
