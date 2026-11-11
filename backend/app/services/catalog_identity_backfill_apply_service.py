"""Opt-in, transaction-bound historical Catalogus identity repair.

Not an API route and never called during startup. The caller must obtain a
reviewed token from a read-only preview and pass a real PostgreSQL connection
inside a managed transaction. No inventory or receipt rows are written.
"""
from __future__ import annotations

import hmac

from sqlalchemy import bindparam, text

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


def apply_selective_reviewed_household_catalog_identity_backfill(
    conn,
    *,
    household_id: str,
    reviewed_plan_token: str,
    reviewed_candidates: list[dict[str, str]],
    expected_eligible: int,
    max_updates: int = 500,
) -> dict:
    """Write *only* individually reviewed eligible pairs, even if other rows
    remain unresolved. The caller owns an explicit PostgreSQL transaction.

    No automatic invocation, API endpoint, startup hook or blanket approval.
    A stale token, edited candidate list, changed owner or partial update
    aborts the whole caller-managed transaction.
    """
    household = str(household_id or "").strip()
    token = str(reviewed_plan_token or "").strip()
    if not household or len(token) != 64 or not all(ch in "0123456789abcdef" for ch in token):
        raise ValueError("A valid household and reviewed plan token are required")
    if conn.dialect.name != "postgresql":
        raise RuntimeError("Historical identity repair requires PostgreSQL")
    if not conn.in_transaction():
        raise RuntimeError("Selective historical identity repair requires a managed transaction")
    if not isinstance(max_updates, int) or not 1 <= max_updates <= 500:
        raise ValueError("max_updates must be between 1 and 500")
    if not isinstance(expected_eligible, int) or not 1 <= expected_eligible <= max_updates:
        raise ValueError("Expected eligible count must be within the reviewed batch limit")
    if not isinstance(reviewed_candidates, list) or len(reviewed_candidates) != expected_eligible:
        raise ValueError("An explicitly reviewed, complete candidate list is required")
    reviewed_pairs = []
    for item in reviewed_candidates:
        if not isinstance(item, dict) or set(item) != {"article_id", "global_product_id"}:
            raise ValueError("Reviewed candidate must contain exact article and product IDs")
        article, product = item["article_id"], item["global_product_id"]
        if not isinstance(article, str) or not article.strip() or not isinstance(product, str) or not product.strip():
            raise ValueError("Reviewed candidate IDs must be nonempty strings")
        reviewed_pairs.append((article, product))
    if len(set(reviewed_pairs)) != len(reviewed_pairs):
        raise ValueError("Duplicate reviewed candidates are not allowed")
    if len({article for article, _ in reviewed_pairs}) != len(reviewed_pairs):
        raise ValueError("One household article cannot receive multiple Catalogus identities")
    if len({product for _, product in reviewed_pairs}) != len(reviewed_pairs):
        raise ValueError("One Catalogus identity cannot be assigned to multiple household articles")

    # Serialize cooperating backfills and lock all household articles before
    # recomputing the exact receipt identity plan. This also protects the
    # absence of an existing Catalogus owner among the locked household rows.
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:household, 671))"),
        {"household": household},
    )
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
    if preview["eligible"] != expected_eligible:
        raise ValueError("Eligible candidate count has changed: review again")
    actual_pairs = {
        (row["article_id"], row["global_product_id"])
        for row in preview["eligible_candidates"]
    }
    if actual_pairs != set(reviewed_pairs):
        raise ValueError("Reviewed candidate identities differ from the live plan")
    # Unresolved or conflicted *other* articles are deliberately excluded from
    # this explicitly reviewed subset, and never modified by the UPDATE.
    updated = 0
    for article, product in sorted(reviewed_pairs):
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
            {"household": household, "article": article, "product": product},
        )
        if changed.rowcount != 1:
            raise RuntimeError(
                "A reviewed article changed during selective repair; rollback required"
            )
        updated += 1
    # Verify the exact identities, not just the rowcount. The caller commits
    # only after this return; exceptions must escape the transaction context.
    verified = conn.execute(
        text("""
            SELECT id, global_product_id FROM household_articles
            WHERE household_id = :household AND id IN :ids
        """).bindparams(bindparam("ids", expanding=True)),
        {"household": household, "ids": [article for article, _ in reviewed_pairs]},
    ).all()
    if set((str(a), str(p)) for a, p in verified) != set(reviewed_pairs):
        raise RuntimeError("Selective repair postcondition failed; rollback required")
    return {
        "household_id": household,
        "reviewed_plan_token": token,
        "eligible": expected_eligible,
        "updated": updated,
        "skipped_conflict": preview["conflict"],
        "skipped_unresolved": preview["unresolved"],
        "skipped_no_identity": preview["no_confirmed_identity"],
        "inventory_changes": 0,
        "receipt_changes": 0,
        "status": "applied",
    }
