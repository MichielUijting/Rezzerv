"""Household-scoped, direct-Catalogus-pair repurchase deduction.

A pair is opt-in by verified identity, never by a household article name. All
reads/writes run inside the caller's receipt transaction. No schema mutation.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.services.product_day_auto_consume_service import (
    AUTO_CONSUME_NONE,
    AUTO_CONSUME_ALL_EXISTING,
    AUTO_CONSUME_PURCHASED_QUANTITY,
    _canonical_purchase_day,
)
from app.services.synonym_auto_consume_identity import confirmed_household_synonym_pair


def _whole(value) -> int:
    number = Decimal(str(value or 0))
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError("Synoniemvoorraad heeft een ongeldig of gebroken aantal")
    return int(number)


def plan_confirmed_synonym_deduction(
    conn,
    *,
    household_id: str,
    purchased_article_id: str,
    purchase_date: str | None,
    purchased_quantity: int,
    household_mode: str,
    effective_mode_for_article,
) -> dict | None:
    """Plan a non-transitive two-article group; None means legacy single-article flow.

    Does not write. The caller must keep the transaction open until the returned
    plan has been applied. A household mode of 'none' never deducts anything.
    """
    if household_mode == AUTO_CONSUME_NONE:
        return None
    day = _canonical_purchase_day(purchase_date)
    if day is None or _whole(purchased_quantity) == 0:
        return None
    household_id = str(household_id)
    purchased_article_id = str(purchased_article_id)
    pair = confirmed_household_synonym_pair(conn, household_id, purchased_article_id)
    if len(pair) != 2 or purchased_article_id not in pair:
        return None

    # Both article rows are locked in deterministic order before any group read.
    # The purchase route already owns the containing transaction.
    member_rows = []
    for article_id in sorted(pair):
        row = conn.execute(text("""
            SELECT id, naam, default_inventory_handling
            FROM household_articles
            WHERE household_id=:household_id AND id=:article_id
              AND COALESCE(status,'active')='active'
            FOR UPDATE
        """), {'household_id': household_id, 'article_id': article_id}).mappings().first()
        if row is None:
            return None
        # Direct-consumption articles must never become a source of stock.
        if str(row.get('default_inventory_handling') or '').upper() == 'DIRECT_CONSUMPTION':
            return None
        member_rows.append(dict(row))

    modes = [effective_mode_for_article(row['id'], row['naam']) for row in member_rows]
    if len(set(modes)) != 1 or modes[0] not in (
        AUTO_CONSUME_PURCHASED_QUANTITY, AUTO_CONSUME_ALL_EXISTING
    ):
        return None
    mode = modes[0]

    # A group is not retroactively rewritten when a newer-dated receipt has
    # already been processed: keep the well-tested single-article fallback.
    recent = conn.execute(text("""
        SELECT MAX(substr(CAST(purchase_date AS TEXT),1,10))
        FROM inventory_events
        WHERE household_id=:household_id
          AND household_article_id IN (:article_a, :article_b)
          AND event_type='purchase' AND source='store_import'
    """), {'household_id': household_id, 'article_a': pair[0], 'article_b': pair[1]}).scalar()
    if recent and str(recent) > day:
        return None

    pre = {}
    prior_purchased = {}
    prior_deducted = {}
    for row in member_rows:
        article_id = str(row['id'])
        total = conn.execute(text("""
            SELECT COALESCE(SUM(aantal), 0)
            FROM inventory
            WHERE household_id=:household_id
              AND household_article_id=:article_id
              AND COALESCE(status,'active')='active'
        """), {'household_id': household_id, 'article_id': article_id}).scalar()
        pre[article_id] = _whole(total)
        events = conn.execute(text("""
            SELECT event_type, source, quantity
            FROM inventory_events
            WHERE household_id=:household_id AND household_article_id=:article_id
              AND substr(trim(COALESCE(CAST(purchase_date AS TEXT),'')),1,10)=:day
              AND ((event_type='purchase' AND source='store_import')
                   OR (event_type='auto_repurchase' AND source='auto_repurchase'))
        """), {'household_id': household_id, 'article_id': article_id, 'day': day}).mappings().all()
        prior_purchased[article_id] = sum(
            _whole(e['quantity']) for e in events if e['event_type'] == 'purchase'
        )
        prior_deducted[article_id] = sum(
            _whole(abs(Decimal(str(e['quantity'] or 0))))
            for e in events if e['event_type'] == 'auto_repurchase'
        )

    total_pre = sum(pre.values())
    total_prior_purchases = sum(prior_purchased.values())
    total_prior_deductions = sum(prior_deducted.values())
    # Today's preceding receipts are added back/removed to recover the
    # start-of-day baseline even when a second shop sells a different synonym.
    start_stock = total_pre - total_prior_purchases + total_prior_deductions
    if start_stock < 0:
        return None  # stock ledger cannot safely establish the baseline
    cumulative = total_prior_purchases + _whole(purchased_quantity)
    if mode == AUTO_CONSUME_ALL_EXISTING:
        desired = start_stock
    else:
        desired = min(start_stock, cumulative)
    requested = max(0, desired - total_prior_deductions)

    # Strict group-wide protection for all earlier purchases on this date.
    old_available = {
        article_id: max(0, pre[article_id] - prior_purchased[article_id])
        for article_id in pair
    }
    requested = min(requested, sum(old_available.values()))
    # Prefer consuming the previously stocked synonym over the newly bought
    # article. Each member's actual event is posted to that member alone.
    order = [article_id for article_id in pair if article_id != purchased_article_id]
    order.append(purchased_article_id)
    allocations = []
    remaining = requested
    for article_id in order:
        quantity = min(remaining, old_available[article_id])
        if quantity:
            allocations.append({'article_id': article_id, 'article_name': next(
                row['naam'] for row in member_rows if row['id'] == article_id
            ), 'quantity': quantity})
            remaining -= quantity

    return {
        'mode': mode,
        'members': tuple(pair),
        'purchase_day': day,
        'requested_deduction_quantity': requested,
        'allocations': allocations,
        'day_start_stock': start_stock,
        'prior_day_purchased_quantity': total_prior_purchases,
        'prior_day_auto_consumed_quantity': total_prior_deductions,
        'cumulative_day_purchased_quantity': cumulative,
    }


def apply_confirmed_synonym_deduction(
    conn,
    *,
    household_id: str,
    purchased_article_id: str,
    purchased_quantity: int,
    purchase_inventory_id: str,
    resolved_location: dict,
    plan: dict,
    create_auto_event,
    apply_stock_consumption,
) -> dict:
    """Apply the plan after the purchase row has been created in one transaction.

    Callers roll the whole receipt transaction back on any mismatch; never
    fabricate a successful history record from a partial stock deduction.
    """
    event_ids = []
    applied = 0
    for item in plan['allocations']:
        article_id = item['article_id']
        quantity = item['quantity']
        protected_quantity = (
            purchased_quantity if article_id == purchased_article_id else 0
        )
        protected_id = (
            purchase_inventory_id if article_id == purchased_article_id else None
        )
        event_id = create_auto_event(
            conn, household_id, article_id, item['article_name'],
            resolved_location, quantity=quantity,
            purchase_date=plan['purchase_day'],
        )
        if not event_id:
            raise RuntimeError('Synoniemafboeking: mutatiebewijs ontbreekt')
        result = apply_stock_consumption(
            conn, household_id, item['article_name'], quantity, resolved_location,
            household_article_id=article_id,
            mode=AUTO_CONSUME_ALL_EXISTING,
            protected_quantity_on_purchase_row=protected_quantity,
            protected_purchase_inventory_id=protected_id,
        )
        if _whole(result.get('applied_quantity')) != quantity:
            raise RuntimeError('Synoniemafboeking: voorraad en mutatiebewijs verschillen')
        event_ids.append(event_id)
        applied += quantity
    if applied != plan['requested_deduction_quantity']:
        raise RuntimeError('Synoniemafboeking: afboeksom is niet volledig verwerkt')
    return {'applied_quantity': applied, 'event_ids': event_ids}
