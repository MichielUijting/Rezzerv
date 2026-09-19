from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import inspect, text

from app.db import engine
from app.services.global_product_service import get_or_create_global_product
from app.services.external_article_confirmation_service import (
    confirm_external_article_for_receipt_item,
)
from app.services.product_inventory_group_store import (
    create_or_get_product_type_with_connection,
    ensure_product_inventory_group_schema,
    link_global_product_to_inventory_group_with_connection,
)


_GTIN_PATTERN = re.compile(r"^[0-9]{8,14}$")
_QUANTITY_PATTERN = re.compile(
    r"(?:(?P<count>[0-9]+)\s*[x×]\s*)?"
    r"(?P<value>[0-9]+(?:[\.,][0-9]+)?)\s*"
    r"(?P<unit>ml|cl|dl|l|mg|g|kg|st(?:uk)?s?)\b",
    re.IGNORECASE,
)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_gtin(value: Any) -> str:
    gtin = re.sub(r"\D+", "", str(value or ""))
    if not _GTIN_PATTERN.fullmatch(gtin):
        raise ValueError("OFF-product bevat geen geldige GTIN van 8 tot en met 14 cijfers")
    return gtin


def _parse_quantity_label(value: Any) -> tuple[float | None, str | None]:
    label = _clean_text(value).lower()
    if not label:
        return None, None
    match = _QUANTITY_PATTERN.search(label)
    if not match:
        return None, None
    try:
        count = Decimal(match.group("count") or "1")
        amount = Decimal(match.group("value").replace(",", ".")) * count
    except InvalidOperation:
        return None, None
    unit = match.group("unit").lower()
    aliases = {"st": "stuk", "stuks": "stuk", "stuks": "stuk"}
    return float(amount), aliases.get(unit, unit)


def _table_columns(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if not inspector.has_table(str(table_name)):
        return set()
    return {
        str(column.get("name") or "")
        for column in inspector.get_columns(str(table_name))
    }


def _table_exists(conn, table_name: str) -> bool:
    return bool(inspect(conn).has_table(str(table_name)))


def _upsert_global_product(conn, off_product: dict[str, Any]) -> tuple[str, str, float | None, str | None]:
    gtin = _normalize_gtin(
        off_product.get("gtin")
        or off_product.get("code")
        or off_product.get("ean")
        or off_product.get("source_product_code")
    )
    product_name = _clean_text(
        off_product.get("product_name")
        or off_product.get("candidate_name")
        or off_product.get("name")
    )
    if not product_name:
        raise ValueError("OFF-productnaam is verplicht")

    brand = _clean_text(off_product.get("brand") or off_product.get("candidate_brand")) or None
    category = _clean_text(
        off_product.get("category")
        or off_product.get("candidate_category")
        or off_product.get("categories")
    ) or None
    quantity_label = _clean_text(
        off_product.get("quantity")
        or off_product.get("quantity_label")
        or off_product.get("net_content")
    )
    size_value, size_unit = _parse_quantity_label(quantity_label)
    image_url = _clean_text(
        off_product.get("image_url")
        or off_product.get("image_front_small_url")
        or off_product.get("image_front_url")
    ) or None

    global_product_id = get_or_create_global_product(
        conn,
        gtin=gtin,
        name=product_name,
        brand=brand,
        variant=_clean_text(off_product.get("variant")) or None,
        category=category,
        size_value=size_value,
        size_unit=size_unit,
        image_url=image_url,
        source="open_food_facts",
        status="active",
        normalize_gtin=lambda value: _normalize_gtin(value),
    )

    identity = conn.execute(
        text(
            """
            SELECT id, global_product_id
            FROM product_identities
            WHERE identity_type = 'gtin' AND identity_value = :gtin
            LIMIT 1
            """
        ),
        {"gtin": gtin},
    ).mappings().first()
    if identity and str(identity.get("global_product_id") or "").strip() not in {"", global_product_id}:
        raise ValueError("GTIN is al aan een ander universeel artikel gekoppeld")
    if identity:
        conn.execute(
            text(
                """
                UPDATE product_identities
                SET global_product_id = :global_product_id,
                    source = 'open_food_facts', confidence_score = 1.0,
                    is_primary = :is_primary, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                "id": identity.get("id"),
                "global_product_id": global_product_id,
                "is_primary": True,
            },
        )
    else:
        conn.execute(
            text(
                """
                INSERT INTO product_identities (
                    id, household_article_id, global_product_id,
                    identity_type, identity_value, source,
                    confidence_score, is_primary, created_at, updated_at
                ) VALUES (
                    :id, '', :global_product_id,
                    'gtin', :gtin, 'open_food_facts',
                    1.0, :is_primary, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "global_product_id": global_product_id,
                "gtin": gtin,
                "is_primary": True,
            },
        )
    return global_product_id, gtin, size_value, size_unit


def _normalize_gpc_source(assignment: dict[str, Any]) -> str:
    explicit = _clean_text(assignment.get("gpc_source")).lower()
    if explicit:
        if explicit not in {"external", "manual"}:
            raise ValueError("gpc_source moet 'external' of 'manual' zijn")
        return explicit

    legacy_source = _clean_text(assignment.get("mapping_source")).lower()
    if "manual" in legacy_source:
        return "manual"
    return "external"


def _official_gpc_brick(conn, brick_code: str) -> dict[str, Any]:
    if not _table_exists(conn, "gpc_bricks"):
        raise ValueError("De officiële GS1 GPC-catalogus is niet beschikbaar")
    row = conn.execute(
        text(
            """
            SELECT
                b.brick_code,
                COALESCE(
                    (
                        SELECT translated_text
                        FROM gpc_translations tr
                        WHERE tr.entity_type = 'brick'
                          AND tr.entity_code = b.brick_code
                          AND tr.language_code = 'nl'
                        LIMIT 1
                    ),
                    b.description
                ) AS display_name
            FROM gpc_bricks b
            WHERE b.brick_code = :brick_code
            LIMIT 1
            """
        ),
        {"brick_code": brick_code},
    ).mappings().first()
    if not row:
        raise ValueError("Onbekende GS1 GPC Brickcode")
    return dict(row)


def _ensure_official_gpc_product_type(conn, brick_code: str) -> str:
    brick = _official_gpc_brick(conn, brick_code)
    product_type_id = f"gpc:{brick_code}"
    existing = conn.execute(
        text(
            """
            SELECT inventory_group_key, gpc_brick_code, source, active
            FROM product_inventory_groups
            WHERE inventory_group_key = :inventory_group_key
            LIMIT 1
            """
        ),
        {"inventory_group_key": product_type_id},
    ).mappings().first()

    if existing:
        existing_brick = _clean_text(existing.get("gpc_brick_code"))
        if existing_brick and existing_brick != brick_code:
            raise ValueError("Bestaand Producttype verwijst naar een andere GS1 GPC Brickcode")
        conn.execute(
            text(
                """
                UPDATE product_inventory_groups
                SET gpc_brick_code = :gpc_brick_code,
                    display_name = COALESCE(NULLIF(display_name, ''), :display_name),
                    source = CASE
                        WHEN source LIKE 'gs1_gpc_%' THEN source
                        ELSE 'gs1_gpc_official'
                    END,
                    active = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE inventory_group_key = :inventory_group_key
                """
            ),
            {
                "inventory_group_key": product_type_id,
                "gpc_brick_code": brick_code,
                "display_name": _clean_text(brick.get("display_name")) or brick_code,
            },
        )
    else:
        conn.execute(
            text(
                """
                INSERT INTO product_inventory_groups (
                    inventory_group_key,
                    display_name,
                    default_base_unit,
                    aggregation_mode,
                    active,
                    gpc_brick_code,
                    source,
                    created_at,
                    updated_at
                ) VALUES (
                    :inventory_group_key,
                    :display_name,
                    'stuk',
                    'count',
                    1,
                    :gpc_brick_code,
                    'gs1_gpc_official',
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "inventory_group_key": product_type_id,
                "display_name": _clean_text(brick.get("display_name")) or brick_code,
                "gpc_brick_code": brick_code,
            },
        )
    return product_type_id


def _resolve_product_type(conn, assignment: dict[str, Any]) -> str:
    if not isinstance(assignment, dict):
        raise ValueError("GS1 GPC-classificatie is verplicht")
    if isinstance(assignment.get("create"), dict):
        raise ValueError("Lokale Producttypen mogen niet vanuit Externe databases worden aangemaakt")

    product_type_id = _clean_text(assignment.get("product_type_id"))
    match = re.fullmatch(r"gpc:(\d{8})", product_type_id)
    if not match:
        raise ValueError("Producttype moet een officiële GS1 GPC Brickcode zijn")

    return _ensure_official_gpc_product_type(conn, match.group(1))


def _persist_global_product_gpc_assignment(
    conn,
    *,
    global_product_id: str,
    brick_code: str,
    gpc_source: str,
    confidence: float,
) -> None:
    if not _table_exists(conn, "global_product_gpc_bricks"):
        raise ValueError("Canonical GPC-classificatieopslag ontbreekt")
    required_columns = {
        "global_product_id",
        "brick_code",
        "assignment_source",
        "confidence",
        "migrated_from",
        "updated_at",
    }
    missing = required_columns - _table_columns(conn, "global_product_gpc_bricks")
    if missing:
        raise ValueError(
            "Canonical GPC-classificatieopslag wijkt af; ontbrekende kolommen: "
            + ", ".join(sorted(missing))
        )
    _official_gpc_brick(conn, brick_code)
    conn.execute(
        text(
            """
            INSERT INTO global_product_gpc_bricks (
                global_product_id,
                brick_code,
                assignment_source,
                confidence,
                migrated_from,
                updated_at
            ) VALUES (
                :global_product_id,
                :brick_code,
                :assignment_source,
                :confidence,
                'external_databases_off_link',
                CURRENT_TIMESTAMP
            )
            ON CONFLICT(global_product_id) DO UPDATE SET
                brick_code = excluded.brick_code,
                assignment_source = excluded.assignment_source,
                confidence = excluded.confidence,
                migrated_from = excluded.migrated_from,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "global_product_id": global_product_id,
            "brick_code": brick_code,
            "assignment_source": gpc_source,
            "confidence": confidence,
        },
    )



def _link_household_article(conn, household_article_id: Any, global_product_id: str) -> str | None:
    article_id = _clean_text(household_article_id)
    if not article_id or article_id.startswith("live::"):
        return None
    article = conn.execute(
        text("SELECT id, global_product_id FROM household_articles WHERE id = :id LIMIT 1"),
        {"id": article_id},
    ).mappings().first()
    if not article:
        return None
    current = _clean_text(article.get("global_product_id"))
    if current and current != global_product_id:
        raise ValueError("Het voorraadartikel is al aan een ander universeel artikel gekoppeld")
    conn.execute(
        text(
            """
            UPDATE household_articles
            SET global_product_id = :global_product_id, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ),
        {"id": article_id, "global_product_id": global_product_id},
    )
    return article_id


def _link_receipt_item(conn, receipt_item_id: str, global_product_id: str) -> dict[str, Any]:
    normalized = _clean_text(receipt_item_id)
    if ":" not in normalized:
        raise ValueError("receipt_item_id heeft geen geldige canonieke prefix")
    prefix, source_id = normalized.split(":", 1)
    source_id = _clean_text(source_id)
    if not source_id:
        raise ValueError("receipt_item_id bevat geen bron-ID")

    if prefix == "purchase-import-line":
        row = conn.execute(
            text(
                """
                SELECT id, matched_household_article_id
                FROM purchase_import_lines WHERE id = :id LIMIT 1
                """
            ),
            {"id": source_id},
        ).mappings().first()
        if not row:
            raise ValueError("Purchase-importregel niet gevonden")
        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET matched_global_product_id = :global_product_id,
                    match_status = 'matched', updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"id": source_id, "global_product_id": global_product_id},
        )
        article_id = _link_household_article(conn, row.get("matched_household_article_id"), global_product_id)
        return {"receipt_item_type": "purchase_import_line", "source_id": source_id, "household_article_id": article_id}

    if prefix == "receipt-table-line":
        row = conn.execute(
            text(
                """
                SELECT
                    rtl.id,
                    rtl.matched_article_id,
                    rtl.external_article_code,
                    COALESCE(
                        rtl.corrected_raw_label,
                        rtl.raw_label,
                        rtl.normalized_label,
                        ''
                    ) AS receipt_text,
                    COALESCE(
                        rt.store_chain,
                        rt.store_name,
                        ''
                    ) AS retailer_code
                FROM receipt_table_lines rtl
                JOIN receipt_tables rt
                  ON rt.id = rtl.receipt_table_id
                WHERE rtl.id = :id
                LIMIT 1
                """
            ),
            {"id": source_id},
        ).mappings().first()
        if not row:
            raise ValueError("Bonregel niet gevonden")
        conn.execute(
            text(
                """
                UPDATE receipt_table_lines
                SET matched_global_product_id = :global_product_id,
                    article_match_status = CASE
                        WHEN COALESCE(matched_article_id, '') <> '' THEN 'matched'
                        ELSE 'product_matched'
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"id": source_id, "global_product_id": global_product_id},
        )
        article_id = _link_household_article(
            conn,
            row.get("matched_article_id"),
            global_product_id,
        )

        return {
            "receipt_item_type": "receipt_table_line",
            "source_id": source_id,
            "household_article_id": article_id,
        }

    if prefix == "receipt-line" and _table_exists(conn, "receipt_lines"):
        columns = _table_columns(conn, "receipt_lines")
        if "matched_global_product_id" not in columns:
            raise ValueError("receipt_lines ondersteunt nog geen universeel-artikelkoppeling")
        row = conn.execute(text("SELECT * FROM receipt_lines WHERE id = :id LIMIT 1"), {"id": source_id}).mappings().first()
        if not row:
            raise ValueError("Receiptregel niet gevonden")
        conn.execute(
            text("UPDATE receipt_lines SET matched_global_product_id = :global_product_id WHERE id = :id"),
            {"id": source_id, "global_product_id": global_product_id},
        )
        article_id = _link_household_article(conn, row.get("matched_article_id"), global_product_id)
        return {"receipt_item_type": "receipt_line", "source_id": source_id, "household_article_id": article_id}

    raise ValueError(f"Niet-ondersteund receipt_item_id-type: {prefix}")


def link_off_product_with_product_type(
    *,
    receipt_item_id: str,
    off_product: dict[str, Any],
    product_type_assignment: dict[str, Any],
    force_failure_after_link: bool = False,
) -> dict[str, Any]:
    """Sla OFF-product, bronkoppeling en Producttype in één transactie op.

    De functie schrijft niet naar external_product_candidates en muteert geen voorraad.
    """
    if not isinstance(off_product, dict):
        raise ValueError("off_product is verplicht")

    ensure_product_inventory_group_schema()
    with engine.begin() as conn:
        global_product_id, gtin, size_value, size_unit = _upsert_global_product(conn, off_product)
        product_type_id = _resolve_product_type(conn, product_type_assignment)
        brick_code = product_type_id.split(":", 1)[1]
        gpc_source = _normalize_gpc_source(product_type_assignment)
        confidence = float(product_type_assignment.get("confidence_score") or 1.0)
        membership = link_global_product_to_inventory_group_with_connection(
            conn,
            global_product_id=global_product_id,
            inventory_group_key=product_type_id,
            comparison_group_key=product_type_id,
            confidence=confidence,
            source=("manual_gs1_gpc" if gpc_source == "manual" else "external_gs1_gpc"),
            confirmed_by_user=True,
        )
        if not membership.get("ok"):
            raise ValueError(str(membership.get("error") or "Producttype kon niet worden gekoppeld"))

        _persist_global_product_gpc_assignment(
            conn,
            global_product_id=global_product_id,
            brick_code=brick_code,
            gpc_source=gpc_source,
            confidence=confidence,
        )

        receipt_link = _link_receipt_item(conn, receipt_item_id, global_product_id)
        confirmed_external_link = confirm_external_article_for_receipt_item(
            conn,
            receipt_item_id=receipt_item_id,
            global_product_id=global_product_id,
            confirmed_by="external_databases_off_link",
        )
        receipt_link["external_article_product_link"] = confirmed_external_link
        if force_failure_after_link:
            raise RuntimeError("Geforceerde rollbackcontrole na OFF-koppeling")

    return {
        "ok": True,
        "linked": True,
        "receipt_item_id": _clean_text(receipt_item_id),
        "receipt_item": receipt_link,
        "global_product": {
            "id": global_product_id,
            "gtin": gtin,
            "name": _clean_text(off_product.get("product_name") or off_product.get("candidate_name") or off_product.get("name")),
            "size_value": size_value,
            "size_unit": size_unit,
            "image_url": _clean_text(
                off_product.get("image_url")
                or off_product.get("image_front_small_url")
                or off_product.get("image_front_url")
            ) or None,
        },
        "product_type": {
            "inventory_group_key": product_type_id,
            "gpc_brick_code": brick_code,
            "gpc_source": gpc_source,
            "confirmed_by_user": True,
        },
        "membership_id": membership.get("membership_id"),
        "creates_external_candidate": False,
        "creates_inventory_event": False,
        "mutates_inventory": False,
    }
