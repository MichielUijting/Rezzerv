"""Conservative household-scoped repair when a retailer code is confirmed.

Uses only exact historical receipt-line references. Never matches names, never
alters quantities/stock/history, never overwrites an existing product identity.
The caller must hold an authorized transaction. The household is always
derived from a trusted authenticated context, never from user-supplied input.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from app.services.catalog_identity_resolution_service import resolve_catalog_identity
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code,
    normalize_external_link_retailer_code,
)


def repair_household_articles_for_confirmed_store_code(
    conn, *, household_id: str, retailer_code: str,
    external_article_code: str, global_product_id: str,
    max_source_rows: int = 10000,
) -> dict:
    """Repair only exact, unique, entirely consistent historical identities."""
    household = str(household_id or "").strip()
    retailer = normalize_external_link_retailer_code(retailer_code)
    code = normalize_external_link_article_code(external_article_code)
    product = str(global_product_id or "").strip()
    if not household or not retailer or not code or not product:
        raise ValueError("Huishouden en bewezen winkelartikelidentiteit zijn verplicht")
    if conn.dialect.name != "postgresql":
        raise RuntimeError("Historical identity repair requires PostgreSQL")
    if not 1 <= max_source_rows <= 10000:
        raise ValueError("Ongeldige limiet voor herstelbronregels")

    # Shared household advisory lock with the reviewed backfill. Lock
    # household articles before inspecting their state.
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:household, 671))"),
        {"household": household},
    )
    conn.execute(
        text("SELECT id FROM household_articles WHERE household_id = :household FOR UPDATE"),
        {"household": household},
    ).all()
    identity = resolve_catalog_identity(
        conn, retailer_code=retailer, external_article_code=code,
    )
    if identity["status"] != "matched" or identity["global_product_id"] != product:
        raise ValueError("Winkelcode heeft geen unieke bevestigde Catalogusidentiteit")

    rows = conn.execute(text("""
        SELECT ha.id AS article_id,
               ha.global_product_id AS current_product_id,
               COALESCE(NULLIF(rt.store_chain, ''), rt.store_name, '') AS retailer,
               rtl.external_article_code AS code,
               rtl.barcode AS gtin
        FROM purchase_import_lines pil
        JOIN purchase_import_batches pib ON pib.id = pil.batch_id
        JOIN receipt_tables rt
          ON rt.id = substr(pib.source_reference, 9)
         AND rt.household_id = pib.household_id
        JOIN receipt_table_lines rtl
          ON rtl.id = substr(pil.external_line_ref, 14)
         AND rtl.receipt_table_id = rt.id
        JOIN household_articles ha
          ON ha.id = pil.matched_household_article_id
         AND ha.household_id = pib.household_id
        WHERE pib.household_id = :household
          AND pib.source_type = 'receipt'
          AND pib.source_reference LIKE 'receipt:%'
          AND pil.external_line_ref LIKE 'receipt-line:%'
          AND rt.deleted_at IS NULL
          AND COALESCE(rtl.is_deleted, FALSE) = FALSE
          AND rtl.line_role = 'product'
          AND CAST(rtl.inventory_eligible AS INTEGER) = 1
        ORDER BY ha.id, rtl.id
        LIMIT :limit
    """), {"household": household, "limit": max_source_rows + 1}).mappings().all()
    if len(rows) > max_source_rows:
        raise ValueError("Onvolledige historische broncontrole; herstel afgebroken")

    grouped: dict[str, list] = defaultdict(list)
    for row in rows:
        grouped[str(row["article_id"])].append(row)

    candidates: list[str] = []
    for article_id, sources in grouped.items():
        belongs_to_code = any(
            normalize_external_link_retailer_code(row["retailer"]) == retailer
            and normalize_external_link_article_code(row["code"]) == code
            for row in sources
        )
        if not belongs_to_code or any(row["current_product_id"] for row in sources):
            continue
        # All original sources pointing at the same household article must
        # independently resolve to the *same* Catalogus product.
        if any(
            (resolution := resolve_catalog_identity(
                conn, gtin=row["gtin"], retailer_code=row["retailer"],
                external_article_code=row["code"],
            ))["status"] != "matched"
            or resolution["global_product_id"] != product
            for row in sources
        ):
            continue
        candidates.append(article_id)

    # A Catalogus product may identify at most one household article per
    # household. Multiple candidates are not arbitrarily merged or selected.
    if len(candidates) != 1:
        return {
            "household_id": household, "source_rows_examined": len(rows),
            "candidates": len(candidates), "updated": 0,
            "status": "ambiguous" if len(candidates) > 1 else "none",
            "stock_changes": 0, "receipt_changes": 0,
        }
    occupied = conn.execute(text("""
        SELECT id FROM household_articles
        WHERE household_id = :household AND global_product_id = :product
          AND id <> :article LIMIT 1
    """), {
        "household": household, "product": product, "article": candidates[0],
    }).first()
    if occupied is not None:
        return {
            "household_id": household, "source_rows_examined": len(rows),
            "candidates": 1, "updated": 0, "status": "already_owned",
            "stock_changes": 0, "receipt_changes": 0,
        }
    result = conn.execute(text("""
        UPDATE household_articles
        SET global_product_id = :product
        WHERE id = :article AND household_id = :household
          AND global_product_id IS NULL
    """), {
        "household": household, "product": product, "article": candidates[0],
    })
    if result.rowcount != 1:
        raise RuntimeError("Huishoudartikelidentiteit is intussen gewijzigd")
    return {
        "household_id": household, "source_rows_examined": len(rows),
        "candidates": 1, "updated": 1, "status": "linked",
        "stock_changes": 0, "receipt_changes": 0,
    }
