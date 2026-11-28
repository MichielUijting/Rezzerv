"""Read-only, household-scoped evidence for unresolved historical onboarding repairs.

Never treat retailer SKU/receipt text as a verified product match. The counts
help explain why a historical replay did not repair older household identities
or a stored consumable flag. No names, SKU values or receipt data are returned.
This module never writes and never authorizes a merge or classification change.
"""
from __future__ import annotations

from collections import defaultdict

from app.integrations.retailer_receipts.normalizer import clean_lidl_transaction_label
from app.services.product_taxonomy_store import infer_food_consumable_from_seed


def summarize_historical_repair_evidence(rows, articles: dict) -> dict:
    """Summarize trusted digital rows; all article IDs belong to the caller's household.

    Retailer code plus normalized description is only a *review candidate*.
    Confirmation by the canonical identity authorities remains mandatory.
    """
    grouped = defaultdict(lambda: {"days": set(), "ids": set()})
    labels_by_code = defaultdict(set)
    observed_ids = set()
    unmatched = 0

    for record in rows:
        row = dict(record)
        if row.get("source_type") != "retailer_api":
            continue
        store = str(row.get("source_provider") or "").lower()
        if store not in {"ah", "jumbo", "lidl"}:
            continue
        article_id = str(row.get("matched_article_id") or "").strip()
        if article_id and article_id in articles:
            observed_ids.add(article_id)
        else:
            unmatched += 1
        sku = str(row.get("external_article_code") or "").strip()
        name = " ".join(str(
            row.get("corrected_raw_label") or row.get("raw_label") or ""
        ).split())
        if store == "lidl":
            name = clean_lidl_transaction_label(name)[0]
        label_key = " ".join(str(name).casefold().split())
        if not sku or not label_key:
            continue
        key = (store, sku, label_key)
        labels_by_code[(store, sku)].add(label_key)
        day = str(row.get("purchase_at") or "")[:10]
        if len(day) == 10:
            grouped[key]["days"].add(day)
        if article_id and article_id in articles:
            grouped[key]["ids"].add(article_id)

    by_catalog = defaultdict(set)
    for article_id, article in articles.items():
        product_id = str(article.get("global_product_id") or "").strip()
        if product_id and str(article.get("global_product_status") or "active").lower() == "active":
            by_catalog[product_id].add(str(article_id))

    food_candidates = sum(
        1 for aid in observed_ids
        if articles[aid].get("consumable") is not None
        and not bool(articles[aid]["consumable"])
        and infer_food_consumable_from_seed(articles[aid].get("naam")) is True
    )

    return {
        "status": "read_only_review_evidence",
        "repeated_sku_description_groups": sum(
            len(group["days"]) >= 2 for group in grouped.values()
        ),
        "split_sku_description_groups": sum(
            len(group["ids"]) > 1 for group in grouped.values()
        ),
        "retailer_sku_description_conflicts": sum(
            len(labels) > 1 for labels in labels_by_code.values()
        ),
        "confirmed_catalog_product_duplicate_groups": sum(
            len(ids) > 1 for ids in by_catalog.values()
        ),
        "taxonomy_food_with_stored_nonconsumable": food_candidates,
        "unlinked_digital_rows": unmatched,
        "physical_inventory_changed": False,
        "household_article_identities_changed": False,
        "requires_canonical_proof_before_merge": True,
    }


def prediction_setting_blockers(conn, household_id: str) -> dict:
    """Report existing settings without silently overriding user preferences."""
    from sqlalchemy import text

    rows = conn.execute(text("""
        SELECT setting_key, setting_value FROM household_settings
        WHERE household_id=:household_id AND setting_key IN (
            'almost_out_prediction_enabled', 'almost_out_prediction_days'
        )
    """), {"household_id": household_id}).mappings().all()
    options = {str(row["setting_key"]): str(row.get("setting_value") or "").strip()
               for row in rows}
    enabled = options.get("almost_out_prediction_enabled")
    normalized = str(enabled or "").strip('"').lower()
    disabled = normalized in {"false", "0", "off", "no", "nee", "uit"}
    try:
        days = int(str(options.get("almost_out_prediction_days") or "").strip('"'))
    except (ValueError, TypeError):
        days = None
    return {
        "prediction_explicitly_stored_disabled": disabled,
        "prediction_days": days,
        "prediction_preference_preserved": True,
    }
