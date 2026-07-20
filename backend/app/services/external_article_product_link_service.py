"""
Gezaghebbende koppelingen tussen winkelartikelen/bonteksten en global_products.

Domeinregel:
- Externe databases bepaalt en bevestigt de koppeling.
- Kassa en Uitpakken mogen deze koppeling later alleen uitlezen.
- Deze service zoekt niet in Open Food Facts.
- Deze service maakt geen household_article of voorraadmutatie aan.
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


def ensure_external_article_product_link_schema(conn) -> None:
    """Maak de koppeltabel en indexen idempotent aan."""
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS external_article_product_links (
                id TEXT PRIMARY KEY,
                retailer_code TEXT NOT NULL,
                receipt_text_normalized TEXT NOT NULL DEFAULT '',
                external_article_code TEXT NOT NULL DEFAULT '',
                global_product_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmed',
                confirmed_by TEXT NULL,
                confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_candidate_id TEXT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK (status IN ('confirmed', 'inactive')),
                CHECK (
                    length(trim(receipt_text_normalized)) > 0
                    OR length(trim(external_article_code)) > 0
                ),
                FOREIGN KEY (global_product_id)
                    REFERENCES global_products(id)
                    ON DELETE RESTRICT
            )
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS
                idx_external_article_product_links_product
            ON external_article_product_links (
                global_product_id,
                status
            )
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS
                idx_external_article_product_links_candidate
            ON external_article_product_links (
                source_candidate_id
            )
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                uq_external_article_product_links_code_confirmed
            ON external_article_product_links (
                retailer_code,
                external_article_code
            )
            WHERE
                status = 'confirmed'
                AND external_article_code <> ''
            """
        )
    )

    conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                uq_external_article_product_links_text_confirmed
            ON external_article_product_links (
                retailer_code,
                receipt_text_normalized
            )
            WHERE
                status = 'confirmed'
                AND receipt_text_normalized <> ''
            """
        )
    )


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
    ensure_external_article_product_link_schema(conn)

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
    ensure_external_article_product_link_schema(conn)

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
                    datetime(link.confirmed_at) DESC,
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
                  AND link.receipt_text_normalized =
                      :receipt_text_normalized
                  AND link.status = 'confirmed'
                  AND lower(COALESCE(gp.status, 'active')) = 'active'
                ORDER BY
                    datetime(link.confirmed_at) DESC,
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