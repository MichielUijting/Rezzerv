from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.global_product_service import get_or_create_global_product
from app.services.external_article_confirmation_service import (
    confirm_external_article_for_receipt_item,
    resolve_external_article_identity,
)
from app.services.external_article_product_link_domain_service import (
    deactivate_global_external_article_product_link,
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
    dialect = str(engine.dialect.name or "").lower()
    if dialect == "sqlite":
        rows = conn.execute(text(f'PRAGMA table_info("{table_name}")')).mappings().all()
        return {str(row.get("name") or "") for row in rows}
    rows = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :table_name"),
        {"table_name": table_name},
    ).mappings().all()
    return {str(row.get("column_name") or "") for row in rows}


def _table_exists(conn, table_name: str) -> bool:
    dialect = str(engine.dialect.name or "").lower()
    if dialect == "sqlite":
        return bool(
            conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name LIMIT 1"),
                {"name": table_name},
            ).scalar()
        )
    return bool(
        conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name = :name LIMIT 1"),
            {"name": table_name},
        ).scalar()
    )


def _upsert_global_product(
    conn,
    off_product: dict[str, Any],
    *,
    source_name: str = "open_food_facts",
) -> tuple[str, str, float | None, str | None]:
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

    global_product_id = get_or_create_global_product(
        conn,
        gtin=gtin,
        name=product_name,
        brand=brand,
        variant=_clean_text(off_product.get("variant")) or None,
        category=category,
        size_value=size_value,
        size_unit=size_unit,
        source=source_name,
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
                    source = :source_name, confidence_score = 1.0,
                    is_primary = 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                "id": identity.get("id"),
                "global_product_id": global_product_id,
                "source_name": source_name,
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
                    'gtin', :gtin, :source_name,
                    1.0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "global_product_id": global_product_id,
                "gtin": gtin,
                "source_name": source_name,
            },
        )
    return global_product_id, gtin, size_value, size_unit


def _resolve_product_type(conn, assignment: dict[str, Any]) -> str:
    if not isinstance(assignment, dict):
        raise ValueError("GS1 GPC-classificatie is verplicht")
    if isinstance(assignment.get("create"), dict):
        raise ValueError("Lokale Producttypen mogen niet vanuit Externe databases worden aangemaakt")

    product_type_id = _clean_text(assignment.get("product_type_id"))
    match = re.fullmatch(r"gpc:(\d{8})", product_type_id)
    if not match:
        raise ValueError("Producttype moet een officiële GS1 GPC Brickcode zijn")

    brick_code = match.group(1)
    product_type = conn.execute(
        text(
            """
            SELECT inventory_group_key, display_name, gpc_brick_code, source
            FROM product_inventory_groups
            WHERE inventory_group_key = :inventory_group_key
              AND gpc_brick_code = :gpc_brick_code
              AND source LIKE 'gs1_gpc_%'
              AND COALESCE(active, 1) = 1
            LIMIT 1
            """
        ),
        {
            "inventory_group_key": product_type_id,
            "gpc_brick_code": brick_code,
        },
    ).mappings().first()
    if not product_type:
        raise ValueError(
            "GS1 GPC Brickcode is niet aanwezig in de officiële Nederlandse GPC-publicatie"
        )
    return product_type_id



def _link_household_article(
    conn,
    household_article_id: Any,
    global_product_id: str,
    *,
    force_relink: bool = False,
) -> str | None:
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
    if current and current != global_product_id and not force_relink:
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


def _link_receipt_item(
    conn,
    receipt_item_id: str,
    global_product_id: str,
    *,
    link_household_article: bool = True,
    force_relink: bool = False,
) -> dict[str, Any]:
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
        household_article_id = _clean_text(
            row.get("matched_household_article_id")
        ) or None
        article_id = (
            _link_household_article(
                conn,
                household_article_id,
                global_product_id,
                force_relink=force_relink,
            )
            if link_household_article
            else household_article_id
        )
        return {
            "receipt_item_type": "purchase_import_line",
            "source_id": source_id,
            "household_article_id": article_id,
        }

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
        household_article_id = _clean_text(
            row.get("matched_article_id")
        ) or None
        article_id = (
            _link_household_article(
                conn,
                household_article_id,
                global_product_id,
                force_relink=force_relink,
            )
            if link_household_article
            else household_article_id
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
        household_article_id = _clean_text(
            row.get("matched_article_id")
        ) or None
        article_id = (
            _link_household_article(
                conn,
                household_article_id,
                global_product_id,
                force_relink=force_relink,
            )
            if link_household_article
            else household_article_id
        )
        return {
            "receipt_item_type": "receipt_line",
            "source_id": source_id,
            "household_article_id": article_id,
        }

    raise ValueError(f"Niet-ondersteund receipt_item_id-type: {prefix}")


def _assert_receipt_item_household(
    conn,
    *,
    receipt_item_id: str,
    household_id: str,
) -> None:
    normalized = _clean_text(receipt_item_id)
    normalized_household_id = _clean_text(household_id)

    if ":" not in normalized:
        raise ValueError("receipt_item_id heeft geen geldige canonieke prefix")

    prefix, source_id = normalized.split(":", 1)
    source_id = _clean_text(source_id)

    if not source_id or not normalized_household_id:
        raise ValueError("Kassabonartikel en actief huishouden zijn verplicht")

    if prefix == "purchase-import-line":
        found = conn.execute(
            text(
                """
                SELECT pil.id
                FROM purchase_import_lines pil
                JOIN purchase_import_batches pib
                  ON pib.id = pil.batch_id
                WHERE pil.id = :source_id
                  AND pib.household_id = :household_id
                LIMIT 1
                """
            ),
            {
                "source_id": source_id,
                "household_id": normalized_household_id,
            },
        ).scalar()
    elif prefix == "receipt-table-line":
        found = conn.execute(
            text(
                """
                SELECT rtl.id
                FROM receipt_table_lines rtl
                JOIN receipt_tables rt
                  ON rt.id = rtl.receipt_table_id
                WHERE rtl.id = :source_id
                  AND rt.household_id = :household_id
                LIMIT 1
                """
            ),
            {
                "source_id": source_id,
                "household_id": normalized_household_id,
            },
        ).scalar()
    elif prefix == "receipt-line" and _table_exists(conn, "receipt_lines"):
        found = conn.execute(
            text(
                """
                SELECT rl.id
                FROM receipt_lines rl
                JOIN receipts r
                  ON r.id = rl.receipt_id
                WHERE rl.id = :source_id
                  AND r.household_id = :household_id
                LIMIT 1
                """
            ),
            {
                "source_id": source_id,
                "household_id": normalized_household_id,
            },
        ).scalar()
    else:
        raise ValueError(f"Niet-ondersteund receipt_item_id-type: {prefix}")

    if not found:
        raise ValueError(
            "Kassabonartikel niet gevonden binnen het actieve huishouden"
        )


def save_barcode_receipt_item(
    *,
    household_id: str,
    receipt_item_id: str,
    gtin: str,
    article_name: str,
) -> dict[str, Any]:
    """Sla een barcode centraal op en koppel alleen het kassabonartikel."""

    normalized_gtin = _normalize_gtin(gtin)
    normalized_article_name = (
        _clean_text(article_name) or f"Product {normalized_gtin}"
    )
    normalized_receipt_item_id = _clean_text(receipt_item_id)

    with engine.begin() as conn:
        _assert_receipt_item_household(
            conn,
            receipt_item_id=normalized_receipt_item_id,
            household_id=household_id,
        )

        inventory_event_count = None
        if _table_exists(conn, "inventory_events"):
            inventory_event_count = conn.execute(
                text("SELECT COUNT(*) FROM inventory_events")
            ).scalar_one()

        global_product_id, stored_gtin, _, _ = _upsert_global_product(
            conn,
            {
                "gtin": normalized_gtin,
                "product_name": normalized_article_name,
            },
            source_name="barcode_scan",
        )

        receipt_link = _link_receipt_item(
            conn,
            normalized_receipt_item_id,
            global_product_id,
            link_household_article=False,
        )

        product = conn.execute(
            text(
                """
                SELECT id, name, brand, status, primary_gtin
                FROM global_products
                WHERE id = :global_product_id
                LIMIT 1
                """
            ),
            {"global_product_id": global_product_id},
        ).mappings().first()

        if _table_exists(conn, "inventory_events"):
            inventory_event_count_after = conn.execute(
                text("SELECT COUNT(*) FROM inventory_events")
            ).scalar_one()

            if inventory_event_count_after != inventory_event_count:
                raise ValueError(
                    "De barcodeopslag heeft onverwacht de voorraad gewijzigd"
                )

        return {
            "ok": True,
            "gtin": stored_gtin,
            "product": {
                "global_product_id": global_product_id,
                "name": (
                    product.get("name")
                    if product
                    else normalized_article_name
                ),
                "brand": product.get("brand") if product else None,
                "status": product.get("status") if product else "active",
                "primary_gtin": (
                    product.get("primary_gtin")
                    if product
                    else stored_gtin
                ),
            },
            "receipt_item": receipt_link,
            "inventory_mutated": False,
            "creates_inventory_event": False,
        }



def unlink_off_product_link(*, receipt_item_id: str) -> dict[str, Any]:
    """Ontkoppel één bonartikel en het gekoppelde huishoudartikel veilig.

    Het centrale catalogusproduct, de GTIN en de officiële GPC-classificatie
    blijven bestaan. Alleen de foutieve bon-/huishoudartikelkoppeling en de
    algemene winkelartikelkoppeling worden beëindigd. Er ontstaat geen
    voorraadmutatie.
    """
    normalized = _clean_text(receipt_item_id)
    if ":" not in normalized:
        raise ValueError("receipt_item_id heeft geen geldige canonieke prefix")

    prefix, source_id = normalized.split(":", 1)
    source_id = _clean_text(source_id)
    if not source_id:
        raise ValueError("receipt_item_id bevat geen bron-ID")

    ensure_product_inventory_group_schema()
    with engine.begin() as conn:
        inventory_before = None
        if _table_exists(conn, "inventory_events"):
            inventory_before = conn.execute(
                text("SELECT COUNT(*) FROM inventory_events")
            ).scalar_one()

        identity = resolve_external_article_identity(conn, normalized)
        household_article_id = None
        global_product_id = None

        if prefix == "purchase-import-line":
            row = conn.execute(
                text(
                    """
                    SELECT matched_household_article_id, matched_global_product_id
                    FROM purchase_import_lines
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
                {"id": source_id},
            ).mappings().first()
            if not row:
                raise ValueError("Purchase-importregel niet gevonden")
            household_article_id = _clean_text(row.get("matched_household_article_id")) or None
            global_product_id = _clean_text(row.get("matched_global_product_id")) or None
            conn.execute(
                text(
                    """
                    UPDATE purchase_import_lines
                    SET matched_global_product_id = NULL,
                        match_status = 'unmatched',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {"id": source_id},
            )
        elif prefix == "receipt-table-line":
            row = conn.execute(
                text(
                    """
                    SELECT matched_article_id, matched_global_product_id
                    FROM receipt_table_lines
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
                {"id": source_id},
            ).mappings().first()
            if not row:
                raise ValueError("Bonregel niet gevonden")
            household_article_id = _clean_text(row.get("matched_article_id")) or None
            global_product_id = _clean_text(row.get("matched_global_product_id")) or None
            conn.execute(
                text(
                    """
                    UPDATE receipt_table_lines
                    SET matched_global_product_id = NULL,
                        article_match_status = CASE
                            WHEN COALESCE(matched_article_id, '') <> '' THEN 'matched'
                            ELSE 'unmatched'
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {"id": source_id},
            )
        elif prefix == "receipt-line" and _table_exists(conn, "receipt_lines"):
            row = conn.execute(
                text("SELECT * FROM receipt_lines WHERE id = :id LIMIT 1"),
                {"id": source_id},
            ).mappings().first()
            if not row:
                raise ValueError("Receiptregel niet gevonden")
            household_article_id = _clean_text(row.get("matched_article_id")) or None
            global_product_id = _clean_text(row.get("matched_global_product_id")) or None
            conn.execute(
                text(
                    "UPDATE receipt_lines SET matched_global_product_id = NULL WHERE id = :id"
                ),
                {"id": source_id},
            )
        else:
            raise ValueError(f"Niet-ondersteund receipt_item_id-type: {prefix}")

        household_article_unlinked = False
        if household_article_id and global_product_id:
            result = conn.execute(
                text(
                    """
                    UPDATE household_articles
                    SET global_product_id = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                      AND global_product_id = :global_product_id
                    """
                ),
                {
                    "id": household_article_id,
                    "global_product_id": global_product_id,
                },
            )
            household_article_unlinked = int(result.rowcount or 0) > 0

        deactivated_links = deactivate_global_external_article_product_link(
            conn,
            retailer_code=identity["retailer_code"],
            receipt_text=identity["receipt_text"],
            external_article_code=identity["external_article_code"],
        )

        if _table_exists(conn, "external_product_candidates"):
            conn.execute(
                text(
                    """
                    UPDATE external_product_candidates
                    SET is_user_confirmed = 0,
                        global_product_id = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE context_key = :receipt_item_id
                       OR purchase_import_line_id = :source_id
                       OR receipt_line_id = :source_id
                    """
                ),
                {
                    "receipt_item_id": normalized,
                    "source_id": source_id,
                },
            )

        if _table_exists(conn, "inventory_events"):
            inventory_after = conn.execute(
                text("SELECT COUNT(*) FROM inventory_events")
            ).scalar_one()
            if inventory_after != inventory_before:
                raise ValueError("Ontkoppelen heeft onverwacht de voorraad gewijzigd")

    return {
        "ok": True,
        "unlinked": True,
        "receipt_item_id": normalized,
        "global_product_id": global_product_id,
        "household_article_id": household_article_id,
        "household_article_unlinked": household_article_unlinked,
        "deactivated_external_links": deactivated_links,
        "catalog_product_deleted": False,
        "product_type_deleted": False,
        "inventory_mutated": False,
        "creates_inventory_event": False,
    }


def link_off_product_with_product_type(
    *,
    receipt_item_id: str,
    off_product: dict[str, Any],
    product_type_assignment: dict[str, Any],
    force_failure_after_link: bool = False,
    force_relink: bool = False,
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
        membership = link_global_product_to_inventory_group_with_connection(
            conn,
            global_product_id=global_product_id,
            inventory_group_key=product_type_id,
            comparison_group_key=product_type_id,
            confidence=float(product_type_assignment.get("confidence_score") or 1.0),
            source=_clean_text(
                product_type_assignment.get("mapping_source") or "user_confirmed_off_result"
            ),
            confirmed_by_user=True,
        )
        if not membership.get("ok"):
            raise ValueError(str(membership.get("error") or "Producttype kon niet worden gekoppeld"))

        receipt_link = _link_receipt_item(
            conn,
            receipt_item_id,
            global_product_id,
            force_relink=force_relink,
        )
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
        },
        "product_type": {
            "inventory_group_key": product_type_id,
            "confirmed_by_user": True,
        },
        "membership_id": membership.get("membership_id"),
        "creates_external_candidate": False,
        "creates_inventory_event": False,
        "mutates_inventory": False,
    }
