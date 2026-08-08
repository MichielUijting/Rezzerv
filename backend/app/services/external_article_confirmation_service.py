"""Brononafhankelijke bevestiging van algemene winkelartikelkoppelingen.

Deze service vertaalt een tijdelijk technisch receipt_item_id naar de stabiele
winkelsleutel. De uiteindelijke opslag blijft bij het centrale domeincontract.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.services.external_article_product_link_domain_service import (
    confirm_global_external_article_product_link,
)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _table_exists(conn, table_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = :name
                LIMIT 1
                """
            ),
            {"name": table_name},
        ).scalar()
    )


def _candidate_identity(conn, receipt_item_id: str, source_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "external_product_candidates"):
        return None
    row = conn.execute(
        text(
            """
            SELECT retailer_code, receipt_line_text, external_article_code, id
            FROM external_product_candidates
            WHERE context_key = :receipt_item_id
               OR purchase_import_line_id = :source_id
               OR receipt_line_id = :source_id
            ORDER BY
                is_user_confirmed DESC,
                CASE WHEN global_product_id IS NOT NULL THEN 1 ELSE 0 END DESC,
                COALESCE(updated_at, created_at, '') DESC,
                id DESC
            LIMIT 1
            """
        ),
        {"receipt_item_id": receipt_item_id, "source_id": source_id},
    ).mappings().first()
    return dict(row) if row else None


def _receipt_table_identity(conn, source_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            """
            SELECT
                COALESCE(rt.store_chain, rt.store_name, '') AS retailer_code,
                COALESCE(
                    rtl.corrected_raw_label,
                    rtl.raw_label,
                    rtl.normalized_label,
                    ''
                ) AS receipt_text,
                COALESCE(rtl.external_article_code, '') AS external_article_code
            FROM receipt_table_lines rtl
            JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
            WHERE rtl.id = :id
            LIMIT 1
            """
        ),
        {"id": source_id},
    ).mappings().first()
    return dict(row) if row else None


def _purchase_import_identity(conn, source_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            """
            SELECT
                pil.article_name_raw AS receipt_text,
                COALESCE(pil.external_article_code, '') AS external_article_code,
                pib.source_reference
            FROM purchase_import_lines pil
            JOIN purchase_import_batches pib ON pib.id = pil.batch_id
            WHERE pil.id = :id
            LIMIT 1
            """
        ),
        {"id": source_id},
    ).mappings().first()
    if not row:
        return None
    result = dict(row)
    result["retailer_code"] = ""
    source_reference = _clean(result.get("source_reference"))
    if source_reference.startswith("receipt:"):
        receipt_table_id = source_reference.split(":", 1)[1]
        receipt = conn.execute(
            text(
                """
                SELECT COALESCE(store_chain, store_name, '') AS retailer_code
                FROM receipt_tables
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": receipt_table_id},
        ).mappings().first()
        if receipt:
            result["retailer_code"] = receipt.get("retailer_code")
    return result


def resolve_external_article_identity(conn, receipt_item_id: str) -> dict[str, Any]:
    normalized = _clean(receipt_item_id)
    if ":" not in normalized:
        raise ValueError("receipt_item_id heeft geen geldige canonieke prefix")
    prefix, source_id = normalized.split(":", 1)
    source_id = _clean(source_id)
    if not source_id:
        raise ValueError("receipt_item_id bevat geen bron-ID")

    identity: dict[str, Any] | None = None
    if prefix == "receipt-table-line":
        identity = _receipt_table_identity(conn, source_id)
    elif prefix == "purchase-import-line":
        identity = _purchase_import_identity(conn, source_id)

    candidate = _candidate_identity(conn, normalized, source_id)
    if candidate:
        if identity is None:
            identity = candidate
        else:
            identity["retailer_code"] = identity.get("retailer_code") or candidate.get("retailer_code")
            identity["receipt_text"] = identity.get("receipt_text") or candidate.get("receipt_line_text")
            identity["external_article_code"] = (
                identity.get("external_article_code") or candidate.get("external_article_code")
            )

    if not identity:
        raise ValueError("Stabiele winkelidentiteit voor bonartikel kon niet worden bepaald")

    retailer_code = _clean(identity.get("retailer_code"))
    receipt_text = _clean(identity.get("receipt_text") or identity.get("receipt_line_text"))
    external_article_code = _clean(identity.get("external_article_code"))
    if not retailer_code:
        raise ValueError("Winkelketen voor algemene koppeling ontbreekt")
    if not receipt_text and not external_article_code:
        raise ValueError("Bonartikeltekst of winkelartikelcode ontbreekt")

    return {
        "retailer_code": retailer_code,
        "receipt_text": receipt_text,
        "external_article_code": external_article_code,
    }


def confirm_external_article_for_receipt_item(
    conn,
    *,
    receipt_item_id: str,
    global_product_id: str,
    confirmed_by: str = "external_databases_off_link",
) -> dict[str, Any]:
    identity = resolve_external_article_identity(conn, receipt_item_id)
    return confirm_global_external_article_product_link(
        conn,
        retailer_code=identity["retailer_code"],
        receipt_text=identity["receipt_text"],
        external_article_code=identity["external_article_code"],
        global_product_id=global_product_id,
        confirmed_by=confirmed_by,
    )
