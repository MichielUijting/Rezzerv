"""
Gezaghebbende koppelingen tussen winkelartikelen/bonteksten en global_products.

Domeinregel:
- Externe databases bepaalt en bevestigt de koppeling.
- Kassa en Uitpakken mogen deze koppeling later alleen uitlezen.
- Deze service zoekt niet in Open Food Facts.
- Deze service maakt geen household_article of voorraadmutatie aan.

Schemaregel:
- Alembic is de enige runtime-authority voor external_article_product_links.
- Deze service leest en schrijft domeindata, maar maakt of wijzigt geen schema.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any, Mapping, Optional

from sqlalchemy import text


CONFIRMED_STATUS = "confirmed"
INACTIVE_STATUS = "inactive"


def normalize_external_link_retailer_code(value: Any) -> str:
    """Normaliseer een winkelcode tot een stabiele technische sleutel."""
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower())
    return normalized.strip("-")


def normalize_external_link_article_code(value: Any) -> str:
    """Normaliseer een winkelartikelcode zonder betekenisvolle tekens te verliezen."""
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def normalize_external_link_receipt_text(value: Any) -> str:
    """
    Normaliseer bontekst uitsluitend als stabiele sleutel.

    Voorbeeld:
    7-GRANEN ONTBIJT -> 7 granen ontbijt
    """
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", " ", normalized.lower())
    return " ".join(normalized.split())


def _complete_global_product_link_data(
    conn,
    global_product_id: str,
) -> dict[str, Any]:
    product_id = str(global_product_id or "").strip()
    if not product_id:
        return {
            "complete": False,
            "reason": "global_product_id ontbreekt",
        }

    row = conn.execute(
        text(
            """
            SELECT
                gp.id,
                gp.name,
                COALESCE(gp.primary_gtin, '') AS primary_gtin,
                EXISTS (
                    SELECT 1
                    FROM product_identities pi
                    WHERE pi.global_product_id = gp.id
                      AND pi.identity_type = 'gtin'
                      AND pi.identity_value = gp.primary_gtin
                ) AS has_matching_gtin_identity,
                EXISTS (
                    SELECT 1
                    FROM product_group_memberships pgm
                    JOIN product_inventory_groups pig
                      ON pig.inventory_group_key = pgm.inventory_group_key
                    WHERE pgm.global_product_id = gp.id
                      AND pgm.active = 1
                      AND length(COALESCE(pig.gpc_brick_code, '')) = 8
                      AND pgm.inventory_group_key = ('gpc:' || pig.gpc_brick_code)
                      AND pig.source LIKE 'gs1_gpc_%'
                      AND COALESCE(pig.active, 1) = 1
                ) AS has_active_official_gpc
            FROM global_products gp
            WHERE gp.id = :global_product_id
            LIMIT 1
            """
        ),
        {"global_product_id": product_id},
    ).mappings().first()

    if not row:
        return {
            "complete": False,
            "reason": "Het universele artikel bestaat niet",
        }

    primary_gtin = str(row.get("primary_gtin") or "").strip()
    has_valid_primary_gtin = bool(
        re.fullmatch(r"[0-9]{8,14}", primary_gtin)
    )
    has_matching_gtin_identity = bool(
        row.get("has_matching_gtin_identity")
    )
    has_active_official_gpc = bool(
        row.get("has_active_official_gpc")
    )

    reasons = []
    if not has_valid_primary_gtin:
        reasons.append("geldige GTIN/EAN ontbreekt")
    if not has_matching_gtin_identity:
        reasons.append("bijpassende GTIN-identiteit ontbreekt")
    if not has_active_official_gpc:
        reasons.append("officieel GS1 GPC-Producttype ontbreekt")

    return {
        "complete": not reasons,
        "reason": "; ".join(reasons),
        "primary_gtin": primary_gtin,
        "has_valid_primary_gtin": has_valid_primary_gtin,
        "has_matching_gtin_identity": has_matching_gtin_identity,
        "has_active_official_gpc": has_active_official_gpc,
    }


def _require_complete_global_product_link(
    conn,
    global_product_id: str,
) -> dict[str, Any]:
    result = _complete_global_product_link_data(
        conn,
        global_product_id,
    )
    if not result.get("complete"):
        raise ValueError(
            "Kassabonartikel kan niet worden gekoppeld: "
            + str(result.get("reason") or "artikelgegevens incompleet")
        )
    return result


def deactivate_incomplete_confirmed_external_links(conn) -> int:
    rows = conn.execute(
        text(
            """
            SELECT id, global_product_id
            FROM external_article_product_links
            WHERE status = 'confirmed'
            ORDER BY id
            """
        )
    ).mappings().all()

    invalid_ids = [
        str(row.get("id") or "")
        for row in rows
        if not _complete_global_product_link_data(
            conn,
            str(row.get("global_product_id") or ""),
        ).get("complete")
    ]

    for link_id in invalid_ids:
        conn.execute(
            text(
                """
                UPDATE external_article_product_links
                SET status = 'inactive',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                  AND status = 'confirmed'
                """
            ),
            {"id": link_id},
        )

    return len(invalid_ids)


def ensure_external_article_product_link_schema(conn) -> None:
    """Legacy compatibility shim; schema authority lives exclusively in Alembic.

    `app.main` still calls this historical symbol during direct module imports.
    It intentionally performs no read, write or DDL. Normal runtime startup is
    guarded by `app.schema_migration_preflight` before Uvicorn imports the app.
    """
    del conn


def _serialize_external_article_product_link(
    row: Optional[Mapping[str, Any]],
) -> Optional[dict[str, Any]]:
    if not row:
        return None

    return {
        "id": str(row.get("id") or ""),
        "retailer_code": str(row.get("retailer_code") or ""),
        "receipt_text_normalized": str(
            row.get("receipt_text_normalized") or ""
        ),
        "external_article_code": str(
            row.get("external_article_code") or ""
        ),
        "global_product_id": str(row.get("global_product_id") or ""),
        "global_product_name": row.get("global_product_name"),
        "status": str(row.get("status") or ""),
        "confirmed_by": row.get("confirmed_by"),
        "confirmed_at": row.get("confirmed_at"),
        "source_candidate_id": row.get("source_candidate_id"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def save_external_article_product_link(
    conn,
    *,
    retailer_code: Any,
    global_product_id: Any,
    receipt_text: Any = None,
    external_article_code: Any = None,
    confirmed_by: Any = None,
    source_candidate_id: Any = None,
) -> dict[str, Any]:
    """
    Sla één bevestigde koppeling op.

    Een nieuwe bevestiging vervangt een eerdere bevestiging voor:
    - dezelfde retailer + winkelartikelcode;
    - dezelfde retailer + genormaliseerde bontekst.
    """
    normalized_retailer = normalize_external_link_retailer_code(
        retailer_code
    )
    normalized_code = normalize_external_link_article_code(
        external_article_code
    )
    normalized_text = normalize_external_link_receipt_text(
        receipt_text
    )
    normalized_product_id = str(global_product_id or "").strip()
    normalized_confirmed_by = (
        str(confirmed_by or "").strip() or None
    )
    normalized_candidate_id = (
        str(source_candidate_id or "").strip() or None
    )

    if not normalized_retailer:
        raise ValueError("retailer_code ontbreekt")

    if not normalized_product_id:
        raise ValueError("global_product_id ontbreekt")

    if not normalized_code and not normalized_text:
        raise ValueError(
            "external_article_code of receipt_text is verplicht"
        )

    product = conn.execute(
        text(
            """
            SELECT id, name, status
            FROM global_products
            WHERE id = :global_product_id
            LIMIT 1
            """
        ),
        {"global_product_id": normalized_product_id},
    ).mappings().first()

    if not product:
        raise ValueError("Het universele artikel bestaat niet")

    if str(product.get("status") or "active").strip().lower() != "active":
        raise ValueError("Het universele artikel is niet actief")

    _require_complete_global_product_link(
        conn,
        normalized_product_id,
    )

    conflict_conditions = []

    if normalized_code:
        conflict_conditions.append(
            """
            (
                retailer_code = :retailer_code
                AND external_article_code = :external_article_code
            )
            """
        )

    if normalized_text:
        conflict_conditions.append(
            """
            (
                retailer_code = :retailer_code
                AND receipt_text_normalized = :receipt_text_normalized
            )
            """
        )

    conflict_where = " OR ".join(conflict_conditions)

    conn.execute(
        text(
            f"""
            UPDATE external_article_product_links
            SET
                status = 'inactive',
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'confirmed'
              AND ({conflict_where})
            """
        ),
        {
            "retailer_code": normalized_retailer,
            "external_article_code": normalized_code,
            "receipt_text_normalized": normalized_text,
        },
    )

    link_id = str(uuid.uuid4())

    conn.execute(
        text(
            """
            INSERT INTO external_article_product_links (
                id,
                retailer_code,
                receipt_text_normalized,
                external_article_code,
                global_product_id,
                status,
                confirmed_by,
                confirmed_at,
                source_candidate_id,
                created_at,
                updated_at
            ) VALUES (
                :id,
                :retailer_code,
                :receipt_text_normalized,
                :external_article_code,
                :global_product_id,
                'confirmed',
                :confirmed_by,
                CURRENT_TIMESTAMP,
                :source_candidate_id,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": link_id,
            "retailer_code": normalized_retailer,
            "receipt_text_normalized": normalized_text,
            "external_article_code": normalized_code,
            "global_product_id": normalized_product_id,
            "confirmed_by": normalized_confirmed_by,
            "source_candidate_id": normalized_candidate_id,
        },
    )

    saved = conn.execute(
        text(
            """
            SELECT
                link.*,
                gp.name AS global_product_name
            FROM external_article_product_links link
            JOIN global_products gp
              ON gp.id = link.global_product_id
            WHERE link.id = :id
            LIMIT 1
            """
        ),
        {"id": link_id},
    ).mappings().first()

    serialized = _serialize_external_article_product_link(saved)

    if not serialized:
        raise RuntimeError(
            "De bevestigde externe artikelkoppeling kon niet worden gelezen"
        )

    return serialized


def get_confirmed_external_article_product_link(
    conn,
    *,
    retailer_code: Any,
    receipt_text: Any = None,
    external_article_code: Any = None,
) -> Optional[dict[str, Any]]:
    """
    Lees een bevestigde koppeling.

    Zoekvolgorde:
    1. retailer + externe artikelcode;
    2. retailer + genormaliseerde bontekst.
    """
    normalized_retailer = normalize_external_link_retailer_code(
        retailer_code
    )
    normalized_code = normalize_external_link_article_code(
        external_article_code
    )
    normalized_text = normalize_external_link_receipt_text(
        receipt_text
    )

    if not normalized_retailer:
        return None

    if normalized_code:
        row = conn.execute(
            text(
                """
                SELECT
                    link.*,
                    gp.name AS global_product_name
                FROM external_article_product_links link
                JOIN global_products gp
                  ON gp.id = link.global_product_id
                WHERE link.retailer_code = :retailer_code
                  AND link.external_article_code = :external_article_code
                  AND link.status = 'confirmed'
                  AND lower(COALESCE(gp.status, 'active')) = 'active'
                ORDER BY
                    link.confirmed_at DESC,
                    link.id DESC
                LIMIT 1
                """
            ),
            {
                "retailer_code": normalized_retailer,
                "external_article_code": normalized_code,
            },
        ).mappings().first()

        if row:
            return _serialize_external_article_product_link(row)

    if normalized_text:
        row = conn.execute(
            text(
                """
                SELECT
                    link.*,
                    gp.name AS global_product_name
                FROM external_article_product_links link
                JOIN global_products gp
                  ON gp.id = link.global_product_id
                WHERE link.retailer_code = :retailer_code
                  AND link.receipt_text_normalized = :receipt_text_normalized
                  AND link.status = 'confirmed'
                  AND lower(COALESCE(gp.status, 'active')) = 'active'
                ORDER BY
                    link.confirmed_at DESC,
                    link.id DESC
                LIMIT 1
                """
            ),
            {
                "retailer_code": normalized_retailer,
                "receipt_text_normalized": normalized_text,
            },
        ).mappings().first()

        if row:
            return _serialize_external_article_product_link(row)

    return None
