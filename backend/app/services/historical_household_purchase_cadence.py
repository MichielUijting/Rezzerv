"""Household-scoped read-only projection of trusted historical repurchase cadence."""
from __future__ import annotations

import json
from sqlalchemy import text


def read_historical_household_purchase_cadence(
    conn, *, household_id: str, household_article_id: str,
) -> dict | None:
    """Only the matching private household article may receive this evidence."""
    owner = str(household_id or "").strip()
    article_id = str(household_article_id or "").strip()
    if not owner or not article_id:
        raise ValueError("Huishouden en huishoudartikel zijn verplicht")
    row = conn.execute(text("""
        SELECT average_repurchase_interval_days, purchase_day_count,
               first_purchase_date, last_purchase_date,
               matched_and_synonyms
        FROM household_historical_purchase_cadences
        WHERE household_id=:household_id
          AND household_article_id=:article_id
        LIMIT 1
    """), {
        "household_id": owner,
        "article_id": article_id,
    }).mappings().first()
    if row is None:
        return None
    members = json.loads(row["matched_and_synonyms"])
    if not isinstance(members, list) or article_id not in members:
        raise ValueError("Historische koopritmeregel mist geldige artikelidentiteit")
    return {
        "average_repurchase_interval_days": float(row["average_repurchase_interval_days"]),
        "purchase_day_count": int(row["purchase_day_count"]),
        "first_purchase_date": str(row["first_purchase_date"])[:10],
        "last_purchase_date": str(row["last_purchase_date"])[:10],
        "matched_and_synonyms": members,
        "basis": "historical_confirmed_identity",
    }
