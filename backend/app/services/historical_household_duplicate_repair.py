"""Conservative, maintenance-owned repair of PROVEN duplicate household identities.

Shared active catalog identity or independent, validated GTINs from original
AH and Jumbo physical receipts may authorize consideration. Retailer SKUs,
receipt descriptions and unchecked barcodes never prove identity.
The transaction owning the historical stock replay is responsible for this
procedure and for recomputing its baselines and cadence after remapping.

A partial group is rolled back to a savepoint. Original receipts and user stock
are never deleted. An old household article is retired with an auditable
redirect, not destroyed. This is intentionally NOT a general arbitrary merge.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.services.historical_household_stock_writer import (
    _block_existing_business_history, _expire_unreferenced_owned_baseline,
    _owned_baselines,
)
from app.services.historical_verified_receipt_gtin import verified_uncataloged_groups
from app.services.receipt_stock_review_service import _checked_gtin_key


class UnsafeHistoricalMerge(ValueError):
    pass


# Only these references may be safely modified by this repair.
_HANDLED_REFERENCES = {
    ("receipt_table_lines", "matched_article_id"),
    ("purchase_import_lines", "matched_household_article_id"),
    ("purchase_import_lines", "suggested_household_article_id"),
    ("store_import_memory", "matched_household_article_id"),
    ("inventory", "household_article_id"),
    ("inventory_events", "household_article_id"),
    ("inventory_events", "article_id"),
    ("household_historical_auto_stock_baselines", "household_article_id"),
    ("household_historical_purchase_cadences", "household_article_id"),
    ("household_article_settings", "household_article_id"),
    ("household_article_notes", "household_article_id"),
}


def _comparable(a: dict, b: dict, *, trusted_gtin: str | None = None) -> bool:
    """Product variants and manual household choices must not be conflated."""
    if trusted_gtin is not None:
        if a.get("global_product_id") or b.get("global_product_id"):
            return False
        for article in (a, b):
            stored = str(article.get("barcode") or "").strip()
            if stored:
                verified = _checked_gtin_key(stored)
                if not verified or verified.zfill(14) != trusted_gtin:
                    return False
    elif not a.get("global_product_id") or a.get("global_product_id") != b.get("global_product_id"):
        return False
    for key in (
        "barcode", "custom_name", "article_group_id",
        "default_inventory_handling", "consumable",
        "min_stock", "ideal_stock",
    ):
        left, right = a.get(key), b.get(key)
        # A manual setting on the losing article must never disappear. A
        # canonical target may safely retain a preference absent on the loser.
        if right not in (None, "") and left != right:
            return False
        if key in {"consumable", "default_inventory_handling"} and left != right:
            return False
    return True


def _unknown_reference_columns(conn):
    """Discover all otherwise unmapped owned article references at runtime."""
    inspector = inspect(conn)
    blocked = []
    for table_name in inspector.get_table_names():
        if table_name in {"household_articles", "alembic_version"}:
            continue
        columns = inspector.get_columns(table_name)
        names = {c["name"] for c in columns}
        owned = {
            name for name in names if name == "household_article_id"
            or name.endswith("_household_article_id")
        }
        for fk in inspector.get_foreign_keys(table_name):
            if fk.get("referred_table") == "household_articles":
                owned.update(fk.get("constrained_columns") or ())
        # article_id is overloaded throughout the schema and is NOT a
        # household identity except in the known inventory event ledger.
        for column in sorted(owned):
            if (table_name, column) not in _HANDLED_REFERENCES:
                blocked.append((table_name, column))
    return blocked


def _quoted(conn, name):
    return conn.dialect.identifier_preparer.quote_identifier(str(name))


def _contains_unknown_refs(conn, article_id, unknown_columns):
    for table_name, column in unknown_columns:
        query = (
            "SELECT 1 FROM " + _quoted(conn, table_name) +
            " WHERE " + _quoted(conn, column) + " = :article_id LIMIT 1"
        )
        if conn.execute(text(query), {"article_id": article_id}).first():
            return True
    return False


def _no_manual_markers(conn, article_id):
    settings = conn.execute(text("""
        SELECT setting_key, setting_value FROM household_article_settings
        WHERE household_article_id = :article_id
    """), {"article_id": article_id}).mappings().all()
    for row in settings:
        if row["setting_key"] != "consumable_origin":
            return False
        try:
            origin = json.loads(row["setting_value"])
        except (ValueError, TypeError):
            return False
        if not isinstance(origin, dict) or origin.get("kind") != "automatic_positive":
            return False
    note = conn.execute(text("""
        SELECT 1 FROM household_article_notes
        WHERE household_article_id = :article_id LIMIT 1
    """), {"article_id": article_id}).first()
    return not note


def _no_override(conn, owner, article_id):
    row = conn.execute(text("""
        SELECT setting_value FROM household_settings
        WHERE household_id=:household_id
          AND setting_key='article_auto_consume_overrides'
    """), {"household_id": owner}).mappings().first()
    if not row or not row["setting_value"]:
        return True
    try:
        overrides = json.loads(row["setting_value"])
    except (ValueError, TypeError):
        return False
    return isinstance(overrides, dict) and article_id not in overrides


def _receipt_source_consistent(conn, owner, old_id, product_id):
    # The uncataloged GTIN route must never absorb another catalog match.
    conflict_condition = (
        "rtl.matched_global_product_id IS NOT NULL"
        if product_id is None else
        "rtl.matched_global_product_id IS NOT NULL AND rtl.matched_global_product_id <> :product_id"
    )
    params = {"household_id": owner, "old_id": old_id}
    if product_id is not None:
        params["product_id"] = product_id
    conflict = conn.execute(text("""
        SELECT 1
        FROM receipt_table_lines rtl
        JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
        WHERE rt.household_id=:household_id
          AND rtl.matched_article_id=:old_id
          AND """ + conflict_condition + """
        LIMIT 1
    """), params).first()
    return conflict is None


def _rewrite_verified_references(conn, owner, old_id, winner_id):
    counts = {}
    counts["receipt_lines"] = int(conn.execute(text("""
        UPDATE receipt_table_lines rtl
        SET matched_article_id = :winner
        FROM receipt_tables rt
        WHERE rtl.receipt_table_id = rt.id
          AND rt.household_id = :household_id
          AND rtl.matched_article_id = :old_id
    """), {
        "household_id": owner, "old_id": old_id, "winner": winner_id,
    }).rowcount or 0)

    for column in ("matched_household_article_id", "suggested_household_article_id"):
        counts[column] = int(conn.execute(text("""
            UPDATE purchase_import_lines pil
            SET """ + column + """ = :winner
            FROM purchase_import_batches pib
            WHERE pil.batch_id = pib.id
              AND pib.household_id = :household_id
              AND pil.""" + column + """ = :old_id
        """), {
            "household_id": owner, "old_id": old_id, "winner": winner_id,
        }).rowcount or 0)

    if inspect(conn).has_table("store_import_memory"):
        counts["store_memory"] = int(conn.execute(text("""
            UPDATE store_import_memory
            SET matched_household_article_id = :winner
            WHERE household_id=:household_id
              AND matched_household_article_id=:old_id
        """), {
            "household_id": owner, "old_id": old_id, "winner": winner_id,
        }).rowcount or 0)
    else:
        counts["store_memory"] = 0
    # Derived cadence is rebuilt from the preserved original physical receipt
    # history in the same outer replay. It is not a manual stock mutation.
    counts["old_cadence"] = int(conn.execute(text("""
        DELETE FROM household_historical_purchase_cadences
        WHERE household_id=:household_id AND household_article_id=:old_id
    """), {
        "household_id": owner, "old_id": old_id,
    }).rowcount or 0)
    return counts


def repair_proven_historical_household_duplicates(conn, *, household_id: str,
                                                   cutoff: str) -> dict:
    """Within the caller's maintenance transaction, merge only zero-risk owners.

    Do not call directly from a client API. Candidate locks, savepoints and
    reversible source retention ensure a failed group never partially changes
    physical receipt or manual data. The caller *must* replay stock/cadence.
    """
    owner = str(household_id or "").strip()
    if not owner or owner == "0" or not str(cutoff or "")[:10]:
        raise ValueError("Geldig huishouden en historische datumgrens vereist")

    originals = conn.execute(text("""
        SELECT ha.*
        FROM household_articles ha
        LEFT JOIN global_products gp ON gp.id = ha.global_product_id
        WHERE ha.household_id=:household_id
          AND COALESCE(ha.status, 'active')='active'
          AND (ha.global_product_id IS NULL OR gp.status='active')
        ORDER BY ha.created_at NULLS LAST, ha.id
        FOR UPDATE OF ha
    """), {"household_id": owner}).mappings().all()
    if len(originals) > 20000:
        raise ValueError("Te veel huishoudartikelen voor bewezen veilig herstel")
    by_product = defaultdict(list)
    for row in originals:
        if row.get("global_product_id") is not None:
            by_product[str(row["global_product_id"])].append(dict(row))
    candidates = [
        (items, "catalog", product_id)
        for product_id, items in by_product.items() if len(items) > 1
    ]
    candidates.extend(
        (items, "checked_gtin", gtin)
        for items, gtin in verified_uncataloged_groups(
            conn, household_id=owner, cutoff=cutoff, articles=originals,
        )
    )
    if not candidates:
        return {"confirmed_groups": 0, "merged": 0, "blocked": 0, "rebound_receipt_lines": 0}

    unknown_columns = _unknown_reference_columns(conn)
    baseline = _owned_baselines(conn, owner)
    merged = blocked = rebound = 0
    for items, proof_kind, proof_id in candidates:
        winner, *losers = items
        product_id = proof_id if proof_kind == "catalog" else None
        checked_gtin = proof_id if proof_kind == "checked_gtin" else None
        # Preserve manual choices of any group member, including the target.
        if any(not _comparable(winner, loser, trusted_gtin=checked_gtin)
               for loser in losers):
            blocked += 1
            continue
        ids = [str(item["id"]) for item in items]
        if _block_existing_business_history(conn, owner, ids):
            blocked += 1
            continue
        safe = True
        for loser in losers:
            old_id = str(loser["id"])
            if (not _no_manual_markers(conn, old_id)
                    or not _no_override(conn, owner, old_id)
                    or _contains_unknown_refs(conn, old_id, unknown_columns)
                    or not _receipt_source_consistent(
                        conn, owner, old_id, product_id
                    )):
                safe = False
                break
        if not safe:
            blocked += 1
            continue

        # The whole group either succeeds or reverts. A stale auto-baseline is
        # not allowed to be forcibly dropped to make a merge pass.
        try:
            group_rebound = group_merged = 0
            with conn.begin_nested():
                for loser in losers:
                    old_id = str(loser["id"])
                    old_baseline = baseline.get(old_id)
                    if old_baseline and not _expire_unreferenced_owned_baseline(
                        conn, owner=owner, article_id=old_id,
                        baseline=old_baseline, cutoff=cutoff,
                    ):
                        raise UnsafeHistoricalMerge("Automatische baseline is niet onaangeroerd")
                    changed = _rewrite_verified_references(
                        conn, owner, old_id, str(winner["id"]),
                    )
                    identity_guard = (
                        "global_product_id IS NULL"
                        if proof_kind == "checked_gtin"
                        else "global_product_id=:product_id"
                    )
                    inactive = conn.execute(text("""
                        UPDATE household_articles
                        SET status='inactive', updated_at=CURRENT_TIMESTAMP
                        WHERE household_id=:household_id AND id=:old_id
                          AND """ + identity_guard + """
                          AND COALESCE(status,'active')='active'
                    """), {
                        "household_id": owner, "old_id": old_id,
                        "product_id": product_id,
                    })
                    if inactive.rowcount != 1:
                        raise UnsafeHistoricalMerge("Oude huishoudidentiteit is gewijzigd")
                    conn.execute(text("""
                        INSERT INTO household_article_settings (
                            id, household_article_id, setting_key, setting_value,
                            created_at, updated_at
                        ) VALUES (
                            :id, :old_id, 'historical_merged_into', :reason,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (household_article_id, setting_key) DO NOTHING
                    """), {
                        "id": str(uuid4()), "old_id": old_id,
                        "reason": json.dumps({
                            "canonical_household_article_id": str(winner["id"]),
                            "confirmed_global_product_id": product_id,
                            "confirmed_receipt_gtin": checked_gtin,
                            "at": datetime.now(timezone.utc).isoformat(),
                            "source": (
                                "historical_catalog_identity_repair"
                                if proof_kind == "catalog"
                                else "historical_verified_receipt_gtin_repair"
                            ),
                        }, sort_keys=True),
                    })
                    group_rebound += changed["receipt_lines"]
                    group_merged += 1
            # The counts must describe COMMITTED savepoints, never attempts.
            rebound += group_rebound
            merged += group_merged
        except (UnsafeHistoricalMerge, IntegrityError):
            blocked += 1
    return {
        "confirmed_groups": len(candidates),
        "merged": merged,
        "blocked": blocked,
        "rebound_receipt_lines": rebound,
    }
