"""Opt-in, transaction-bound historical Catalogus identity repair.

Not an API route and never called during startup. The caller must obtain a
reviewed token from a read-only preview and pass a real PostgreSQL connection
inside a managed transaction. No inventory or receipt rows are written.
"""
from __future__ import annotations

import hmac

from sqlalchemy import text

from app.services.catalog_identity_backfill_preview_service import (
    preview_household_catalog_identity_backfill,
)


def apply_reviewed_household_catalog_identity_backfill(
    conn,
    *,
    household_id: str,
    reviewed_plan_token: str,
    max_updates: int = 500,
) -> dict:
    """Apply only an unchanged, complete and non-conflicting reviewed plan.

    Calling this requires a separately authorized operator workflow; the
    service does not accept or grant roles, and is intentionally not exposed
    through an unauthenticated endpoint.
    """
    household = str(household_id or "").strip()
    token = str(reviewed_plan_token or "").strip()
    if not household or len(token) != 64 or not all(ch in "0123456789abcdef" for ch in token):
        raise ValueError("A valid household and reviewed plan token are required")
    if conn.dialect.name != "postgresql":
        raise RuntimeError("Historical repair requires PostgreSQL")
    if max_updates < 1 or max_updates > 500:
        raise ValueError("max_updates must be between 1 and 500")

    # Serialize cooperating backfills for this household. Also lock the
    # article records to prevent concurrent identity writes during recheck.
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:household, 671))"),
                 {"household": household})
    conn.execute(
        text("SELECT id FROM household_articles WHERE household_id = :household FOR UPDATE"),
        {"household": household},
    ).all()

    preview = preview_household_catalog_identity_backfill(
        conn, household_id=household, include_candidates=True,
    )
    if preview["limited"]:
        raise ValueError("The historical scan is incomplete")
    if not hmac.compare_digest(preview["plan_token"], token):
        raise ValueError("Historical identity plan has changed: review again")
    candidates = preview["eligible_candidates"]
    if len(candidates) > max_updates:
        raise ValueError("Reviewed plan exceeds the maximum batch size")
    if preview["conflict"] or preview["unresolved"]:
        # Never apply part of a reviewed plan while any disputed source
        # identity remains unresolved.
        raise ValueError("Historical identity conflicts must be reviewed first")

    updated = 0
    for row in candidates:
        changed = conn.execute(
            text("""
                UPDATE household_articles ha
                SET global_product_id = :product
                WHERE ha.id = :article AND ha.household_id = :household
                  AND ha.global_product_id IS NULL
                  AND EXISTS (
                      SELECT 1 FROM global_products gp
                      WHERE gp.id = :product
                        AND LOWER(COALESCE(gp.status, 'active')) = 'active'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM household_articles other
                      WHERE other.household_id = :household
                        AND other.id <> ha.id
                        AND other.global_product_id = :product
                  )
            """),
            {"household": household, "article": row["article_id"],
             "product": row["global_product_id"]},
        )
        if changed.rowcount != 1:
            # Caller must roll the surrounding transaction back. A managed
            # transaction rolls back when this exception leaves its context.
            raise RuntimeError("Candidate changed during historical identity repair")
        updated += 1

    return {
        "household_id": household,
        "reviewed_plan_token": token,
        "eligible": len(candidates),
        "updated": updated,
        "inventory_changes": 0,
        "receipt_changes": 0,
        "status": "applied" if updated else "no_changes",
    }
