"""Durable, explicitly confirmed opening-stock decisions (PR3).

Opening-stock choices are not receipt imports. No stock is created by GET or
historical analysis. The only write requires an authorized household admin,
a fresh exact proposal, and an explicit confirmation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re
import uuid

from fastapi import HTTPException
from sqlalchemy import text

from app.services.canonical_inventory_identity_service import (
    apply_inventory_purchase_by_identity,
    ensure_locationless_inventory_identity_guard,
    require_household_article,
)
from app.services.receipt_historical_learning_service import (
    MAX_SOURCE_ROWS,
    load_historical_learning,
)

MAX_CONFIRMED_QUANTITY = 10000
_REVISION_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def proposal_revision(item: dict, cutoff: str | None) -> str:
    """Stable revision of the exact source evidence shown to the reviewer."""
    proof = {
        "cutover": cutoff,
        "key": item.get("key"),
        "unit": item.get("unit"),
        "article": item.get("household_article_id"),
        "product_ids": item.get("product_ids"),
        "source_fingerprint": item.get("source_fingerprint"),
        "source_receipt_count": item.get("source_receipt_count"),
        "purchase_day_count": item.get("purchase_day_count"),
        "last_purchase_date": item.get("last_purchase_date"),
        "estimated_opening_quantity": item.get("estimated_opening_quantity"),
        "estimate_status": item.get("estimate_status"),
    }
    return sha256(json.dumps(proof, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_opening_stock_quantity(value: object) -> int:
    """Never truncate a decimal quantity into physical stock units."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise HTTPException(status_code=422, detail="Vul een heel aantal stuks in.")
    if value < 0 or value > MAX_CONFIRMED_QUANTITY:
        raise HTTPException(status_code=422, detail="Aantal moet tussen 0 en 10.000 liggen.")
    return value


def _decision(conn, household_id: str, article_id: str) -> dict | None:
    row = conn.execute(text("""
        SELECT id, proposal_key, proposal_revision, confirmed_quantity, inventory_id,
               inventory_event_id, confirmed_at
        FROM household_opening_stock_confirmations
        WHERE household_id = :household_id AND household_article_id = :article_id
        LIMIT 1
    """), {"household_id": household_id, "article_id": article_id}).mappings().first()
    return dict(row) if row else None


def _has_existing_stock_history(conn, household_id: str, article_id: str) -> bool:
    # A zero inventory row or a past event is still evidence of active stock
    # handling; no new baseline may be synthesized over it.
    inventory = conn.execute(text("""
        SELECT 1 FROM inventory
        WHERE household_id = :household_id AND household_article_id = :article_id
        LIMIT 1
    """), {"household_id": household_id, "article_id": article_id}).scalar()
    if inventory:
        return True
    event = conn.execute(text("""
        SELECT 1 FROM inventory_events
        WHERE household_id = :household_id
          AND (household_article_id = :article_id OR article_id = :article_id)
        LIMIT 1
    """), {"household_id": household_id, "article_id": article_id}).scalar()
    return bool(event)


def _safe_single_article_binding(item: dict, article: dict) -> bool:
    article_id = str(article.get("id") or "").strip()
    key = str(item.get("key") or "")
    if not article_id or article_id != str(item.get("household_article_id") or "").strip():
        return False
    if key == "article:" + article_id:
        return True
    product_ids = item.get("product_ids") or []
    if len(product_ids) != 1 or key != "product:" + str(product_ids[0]):
        return False
    # Every included historical source line must explicitly own the same
    # article. Product-wide evidence from unassigned or another household
    # is not proof of physical stock for this household article.
    if (not item.get("source_line_count")
            or item.get("owned_line_count") != item.get("source_line_count")):
        return False
    return str(article.get("global_product_id") or "") == str(product_ids[0])


def _review_item(conn, *, household_id: str, cutoff: str | None, item: dict) -> dict:
    result = dict(item)
    article_id = str(item.get("household_article_id") or "").strip()
    result["proposal_revision"] = proposal_revision(item, cutoff)
    result["can_confirm"] = False
    result["review_status"] = "identity_review_required"
    result["confirmed_quantity"] = None
    result["confirmed_at"] = None
    if not article_id:
        # The source may be a global product or a synonym group; its display
        # identity does not prove a single household stock identity.
        return result
    if item.get("unit") != "stuk":
        result["review_status"] = "unit_review_required"
        return result

    owned = conn.execute(text("""
        SELECT id, global_product_id FROM household_articles
        WHERE household_id = :household_id AND id = :article_id
          AND COALESCE(status, 'active') = 'active'
        LIMIT 1
    """), {"household_id": household_id, "article_id": article_id}).mappings().first()
    if not owned:
        result["review_status"] = "article_unavailable"
        return result
    if not _safe_single_article_binding(item, owned):
        result["review_status"] = "identity_review_required"
        return result

    prior = _decision(conn, household_id, article_id)
    if prior:
        result["review_status"] = "confirmed"
        result["confirmed_quantity"] = int(prior["confirmed_quantity"])
        result["confirmed_at"] = (
            prior["confirmed_at"].isoformat()
            if hasattr(prior["confirmed_at"], "isoformat") else str(prior["confirmed_at"])
        )
        return result

    if _has_existing_stock_history(conn, household_id, article_id):
        result["review_status"] = "existing_stock"
        return result

    result["can_confirm"] = True
    result["review_status"] = "awaiting_manual_confirmation"
    return result


def list_opening_stock_reviews(conn, *, household_id: str, page: int = 1, page_size: int = 10) -> dict:
    """Read-only: no creation of articles, cutovers, stock or approval state."""
    projection = load_historical_learning(
        conn, household_id=household_id, page=page, page_size=page_size,
    )
    cutoff = projection.get("first_current_purchase_date")
    projection["items"] = [
        _review_item(conn, household_id=household_id, cutoff=cutoff, item=item)
        for item in projection["items"]
    ]
    return projection


def confirm_opening_stock(
    conn, *, household_id: str, actor_user_id: str,
    proposal_key: str, proposal_revision_value: str,
    household_article_id: str, confirmed_quantity: int,
    explicitly_confirmed: bool,
) -> dict:
    """Atomic idempotent confirmation, caller owns authorization and transaction."""
    if explicitly_confirmed is not True:
        raise HTTPException(status_code=400, detail="Bevestig de beginvoorraad expliciet.")
    quantity = validate_opening_stock_quantity(confirmed_quantity)
    owner = str(household_id or "").strip()
    actor = str(actor_user_id or "").strip()
    article_id = str(household_article_id or "").strip()
    key = str(proposal_key or "").strip()
    revision = str(proposal_revision_value or "").strip().lower()
    if not owner or owner == "0" or not actor or not article_id:
        raise HTTPException(status_code=403, detail="Geen geldig huishouden of actor.")
    if not key.startswith(("article:", "product:")) or not _REVISION_PATTERN.fullmatch(revision):
        raise HTTPException(status_code=409, detail="Artikel of voorstel ongeldig; laad opnieuw.")

    # Serialise concurrent confirmations for this canonical household article.
    article = conn.execute(text("""
        SELECT id, naam, global_product_id FROM household_articles
        WHERE id = :article_id AND household_id = :household_id
          AND COALESCE(status, 'active') = 'active'
        FOR UPDATE
    """), {"article_id": article_id, "household_id": owner}).mappings().first()
    if not article:
        raise HTTPException(status_code=409, detail="Huishoudartikel niet meer beschikbaar.")

    prior = _decision(conn, owner, article_id)
    if prior:
        if (prior["proposal_key"] == key and prior["proposal_revision"] == revision
                and int(prior["confirmed_quantity"]) == quantity):
            return {"status": "already_confirmed", "quantity": quantity, "household_article_id": article_id}
        raise HTTPException(status_code=409, detail="Beginvoorraad is al eerder bevestigd.")

    # Recompute while owning the article lock; a changed receipt or match
    # invalidates the revision shown in the open tab.
    projection = load_historical_learning(
        conn, household_id=owner, page=1, page_size=MAX_SOURCE_ROWS,
    )
    if projection.get("status") != "analysis_only":
        raise HTTPException(status_code=409, detail="Historische analyse niet beschikbaar.")
    matching = [item for item in projection["items"] if item.get("key") == key]
    if len(matching) != 1:
        raise HTTPException(status_code=409, detail="Voorstel niet meer eenduidig; laad opnieuw.")
    item = matching[0]
    if item.get("unit") != "stuk" or not _safe_single_article_binding(item, article):
        raise HTTPException(status_code=409, detail="Artikel of eenheid niet veilig bevestigbaar.")
    if proposal_revision(item, projection.get("first_current_purchase_date")) != revision:
        raise HTTPException(status_code=409, detail="Historische aankoopgegevens zijn gewijzigd; laad opnieuw.")

    require_household_article(conn, owner, article_id)
    if _has_existing_stock_history(conn, owner, article_id):
        raise HTTPException(status_code=409, detail="Er bestaat al voorraadhistorie; gebruik Voorraad voor correcties.")

    confirmation_id = uuid.uuid4().hex
    inventory_id = None
    event_id = None
    if quantity:
        ensure_locationless_inventory_identity_guard(conn)
        # Existing canonical locationless writer; the article was already
        # validated and no location is required by this workflow.
        inventory_id = apply_inventory_purchase_by_identity(
            conn, household_id=owner, household_article_id=article_id,
            quantity=quantity, space_id=None, sublocation_id=None,
        )
        event_id = uuid.uuid4().hex
        recorded_at = datetime.now(timezone.utc)
        effective_at = str(projection["first_current_purchase_date"]) + "T00:00:00+00:00"
        conn.execute(text("""
            INSERT INTO inventory_events (
                id, household_id, article_id, household_article_id, article_name,
                location_id, location_label, event_type, quantity, old_quantity,
                new_quantity, source, note, effective_at, recorded_at,
                effective_at_precision, event_priority, source_reference, created_at
            ) VALUES (
                :id, :household_id, :article_id, :article_id, :article_name,
                NULL, NULL, 'baseline', :quantity, 0,
                :quantity, 'historical_opening_stock_confirmation',
                'Door huishoudbeheerder bevestigde beginvoorraad uit historische aankoopanalyse',
                :effective_at, :recorded_at, 'date', 0, :source_reference, CURRENT_TIMESTAMP
            )
        """), {
            "id": event_id, "household_id": owner, "article_id": article_id,
            "article_name": str(article["naam"]), "quantity": quantity,
            "effective_at": effective_at, "recorded_at": recorded_at,
            "source_reference": "historical-opening:" + confirmation_id,
        })

    conn.execute(text("""
        INSERT INTO household_opening_stock_confirmations (
            id, household_id, household_article_id, proposal_key, proposal_revision,
            source_fingerprint, first_current_purchase_date, confirmed_quantity,
            confirmed_by_user_id, inventory_id, inventory_event_id, confirmed_at
        ) VALUES (
            :id, :household_id, :article_id, :proposal_key, :proposal_revision,
            :source_fingerprint, :cutover, :quantity,
            :actor, :inventory_id, :event_id, CURRENT_TIMESTAMP
        )
    """), {
        "id": confirmation_id, "household_id": owner, "article_id": article_id,
        "proposal_key": key, "proposal_revision": revision,
        "source_fingerprint": str(item.get("source_fingerprint") or ""),
        "cutover": projection["first_current_purchase_date"],
        "quantity": quantity, "actor": actor,
        "inventory_id": inventory_id, "event_id": event_id,
    })
    return {
        "status": "confirmed",
        "household_article_id": article_id,
        "quantity": quantity,
        "inventory_created": quantity > 0,
    }
